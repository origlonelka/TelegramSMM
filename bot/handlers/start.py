from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from core.config import ADMIN_IDS, ADMIN_USERNAMES
from bot.keyboards.inline import main_menu_kb

router = Router()

WELCOME_TEXT = (
    "🤖 <b>TelegramSMM</b>\n\n"
    "Бот для автоматической отправки комментариев в каналы.\n\n"
    "Выберите раздел:"
)


@router.message(CommandStart())
async def cmd_start(message: Message):
    username = (message.from_user.username or "").lower()
    if message.from_user.id not in ADMIN_IDS and username not in ADMIN_USERNAMES:
        await message.answer("⛔ У вас нет доступа к этому боту.")
        return
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_kb(), parse_mode="HTML")
    await callback.answer()

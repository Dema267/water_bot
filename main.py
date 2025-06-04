import os
import logging
import asyncio
import random
from datetime import datetime, timedelta
from typing import Dict, Any

import pytz
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart, Command
from aiogram import Router

# Загрузка переменных из .env
load_dotenv()
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not API_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан в .env файле")

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и хранилища
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

# Хранилище пользователей (замените на БД в проде)
user_data: Dict[int, Dict[str, Any]] = {}

# Список фактов
WATER_FACTS = [
    "Вода составляет около 60% массы тела взрослого человека.",
    "Даже легкое обезвоживание может вызвать усталость и головную боль.",
    "Вода помогает регулировать температуру тела.",
    "Питье воды может улучшить концентрацию и когнитивные функции.",
    "Вода помогает выводить токсины из организма через почки.",
    "Достаточное потребление воды может улучшить состояние кожи.",
    "Вода смазывает суставы и уменьшает трение между костями.",
    "Человек может прожить без воды всего 3-5 дней.",
    "Вода помогает пищеварению и предотвращает запоры.",
    "Питье воды перед едой может помочь в контроле веса.",
]

# Состояния
class UserStates(StatesGroup):
    waiting_for_weight = State()
    waiting_for_age = State()
    waiting_for_water_intake = State()

# Подсчёт дневной нормы
def calculate_daily_water_needs(weight: float, age: int) -> float:
    base = weight * 0.033
    if age < 30:
        return base
    elif age < 55:
        return base * 0.95
    return base * 0.9

# Отправка напоминания
async def send_water_reminder(user_id: int):
    if user_id not in user_data:
        return

    user = user_data[user_id]
    now = datetime.now(pytz.utc)

    if user.get('daily_intake', 0) >= user['daily_need']:
        await bot.send_message(
            user_id,
            f"🎉 Вы уже выпили достаточно воды сегодня!\n"
            f"Всего: {user['daily_intake']:.1f} л из {user['daily_need']:.1f} л"
        )
        return

    await bot.send_message(
        user_id,
        f"💧 Напоминание выпить воды!\n"
        f"Вы выпили {user['daily_intake']:.1f} л из {user['daily_need']:.1f} л\n"
        f"Введите количество в мл (например: 250)"
    )
    user_data[user_id]['last_reminder'] = now

# Планировщик напоминаний
async def schedule_reminders():
    while True:
        now = datetime.now(pytz.utc)
        for user_id, user in user_data.items():
            last = user.get("last_reminder")
            if not last or (now - last) > timedelta(hours=2):
                await send_water_reminder(user_id)
        await asyncio.sleep(60)

# Команда /start и /help
@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start(message: Message, state: FSMContext):
    await message.answer(
        "🚰 *Water Reminder Bot*\n"
        "/start — Начать\n"
        "/help — Помощь\n"
        "/info — О боте\n"
        "/fact — Факт о воде\n"
        "/total — Сколько выпито сегодня\n"
        "Бот будет напоминать пить воду каждые 2 часа.",
        parse_mode="Markdown"
    )

    if message.from_user.id not in user_data:
        await message.answer("Введите ваш вес в кг:")
        await state.set_state(UserStates.waiting_for_weight)

# Команда /info
@router.message(Command("info"))
async def cmd_info(message: Message):
    await message.answer(
        "💧 Этот бот поможет вам следить за потреблением воды.\n"
        "Введите вес и возраст — и бот рассчитает норму воды на день и будет напоминать каждые 2 часа.",
        parse_mode="Markdown"
    )

# Команда /fact
@router.message(Command("fact"))
async def cmd_fact(message: Message):
    fact = random.choice(WATER_FACTS)
    await message.answer(f"💧 Факт о воде:\n\n{fact}")

# Команда /total
@router.message(Command("total"))
async def cmd_total(message: Message):
    user_id = message.from_user.id
    if user_id not in user_data:
        await message.answer("Сначала укажите вес и возраст: /start")
        return

    user = user_data[user_id]
    intake = user.get("daily_intake", 0)
    need = user["daily_need"]
    remain = max(0, need - intake)

    if intake >= need:
        text = f"🎉 Вы выпили достаточно: {intake:.1f} л из {need:.1f} л"
    else:
        text = f"💧 Выпито: {intake:.1f} л из {need:.1f} л\nОсталось: {remain:.1f} л"

    await message.answer(text)

# Вес
@router.message(UserStates.waiting_for_weight)
async def process_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text)
        if not (1 <= weight <= 300):
            raise ValueError()
        await state.update_data(weight=weight)
        await message.answer("Теперь введите возраст:")
        await state.set_state(UserStates.waiting_for_age)
    except:
        await message.answer("Введите корректный вес в кг (например 70):")

# Возраст
@router.message(UserStates.waiting_for_age)
async def process_age(message: Message, state: FSMContext):
    try:
        age = int(message.text)
        if not (1 <= age <= 120):
            raise ValueError()
        data = await state.get_data()
        weight = data["weight"]
        daily_need = calculate_daily_water_needs(weight, age)
        user_data[message.from_user.id] = {
            "weight": weight,
            "age": age,
            "daily_need": daily_need,
            "daily_intake": 0,
            "history": [],
            "last_reminder": None
        }
        await state.clear()
        await message.answer(f"Ваша дневная норма: {daily_need:.1f} л. Бот будет напоминать пить воду!")
    except:
        await message.answer("Введите корректный возраст (например 25):")

# Приём воды
@router.message(F.text.regexp(r"^\d+(\.\d+)?$"))
async def handle_water_intake(message: Message, state: FSMContext):
    try:
        user_id = message.from_user.id
        if user_id not in user_data:
            await message.answer("Сначала введите вес и возраст: /start")
            return

        amount_ml = float(message.text)
        if amount_ml <= 0:
            raise ValueError()

        amount_l = amount_ml / 1000
        user = user_data[user_id]
        user["daily_intake"] += amount_l
        user["history"].append({"time": datetime.now(pytz.utc), "amount": amount_l})

        remain = max(0, user["daily_need"] - user["daily_intake"])

        if user["daily_intake"] >= user["daily_need"]:
            text = f"🎉 Вы достигли нормы!\nВсего: {user['daily_intake']:.1f} л"
        else:
            text = f"💧 Добавлено {amount_ml} мл\nВсего: {user['daily_intake']:.1f} л\nОсталось: {remain:.1f} л"

        await message.answer(text)
    except:
        await message.answer("Введите количество воды в мл (например 250):")

# Прочие сообщения
@router.message()
async def unknown(message: Message):
    await message.answer("Неизвестная команда. Используйте /help")

# Старт бота
async def main():
    dp.include_router(router)
    asyncio.create_task(schedule_reminders())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

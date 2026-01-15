"""
Бот для расписания намазов в Черкесске (КЧР)
Автор: [Ваше имя/организация]
Версия: 1.1 (с улучшениями: уведомления, напоминания, выбор намазов, SQLite, логи)

Основные функции:
1. Показ расписания на сегодня/завтра
2. Показ расписания на месяц
3. Уведомления о времени намазов (с напоминанием за 10 мин)
4. Статус текущего намаза
5. Выбор конкретных намазов для уведомлений
"""

import asyncio
import os
import csv
import json
import logging
from datetime import datetime, timedelta
import sqlite3

# Импорты для Telegram бота
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# Импорты для планировщика уведомлений
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Импорты для конфигурации
from dotenv import load_dotenv
import pytz

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ====================
try:
    load_dotenv()
except:
    logger.warning(".env файл не найден, используем системные переменные")

# ==================== НАСТРОЙКИ И КОНФИГУРАЦИЯ ====================
API_TOKEN = os.getenv('API_TOKEN') or os.environ.get('API_TOKEN')

if not API_TOKEN:
    logger.critical("Не найден API_TOKEN!")
    exit(1)

# Названия файлов с данными
CSV_FILE = 'prayer_times_cherkessk.csv'
SUBSCRIPTIONS_DB = 'subscriptions.db'  # Теперь используем SQLite вместо JSON

# Устанавливаем часовой пояс
TIMEZONE = pytz.timezone('Europe/Moscow')

# Словарь с русскими названиями месяцев
MONTHS_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

# Словарь с русскими названиями намазов
PRAYER_NAMES = {
    'Fajr': 'Фаджр',
    'Sunrise': 'Восход',
    'Duhr': 'Зухр', 
    'Asr': 'Аср',
    'Maghrib': 'Магриб',
    'Isha': 'Иша'
}

# Порядок намазов
PRAYER_ORDER_MONTH = ['Fajr', 'Duhr', 'Asr', 'Maghrib', 'Isha']
DETAILED_PRAYER_ORDER = ['Fajr', 'Sunrise', 'Duhr', 'Asr', 'Maghrib', 'Isha', 'FirstThird', 'Midnight', 'LastThird']
TIME_PRAYER_ORDER = ['Fajr', 'Duhr', 'Asr', 'Maghrib', 'Isha']

# ==================== ИНИЦИАЛИЗАЦИЯ КОМПОНЕНТОВ ====================
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

# Глобальные переменные
prayer_data = {}
subscriptions = {}  # dict: user_id -> set of prayers (e.g., {'Fajr', 'Duhr'})

# ==================== РАБОТА С БАЗОЙ ДАННЫХ (SQLite) ====================
def init_db():
    conn = sqlite3.connect(SUBSCRIPTIONS_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            user_id INTEGER PRIMARY KEY,
            prayers TEXT  -- JSON-encoded set of prayers
        )
    ''')
    conn.commit()
    conn.close()

def load_subscriptions():
    global subscriptions
    conn = sqlite3.connect(SUBSCRIPTIONS_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, prayers FROM subscriptions')
    rows = cursor.fetchall()
    for user_id, prayers_json in rows:
        subscriptions[user_id] = set(json.loads(prayers_json)) if prayers_json else set(TIME_PRAYER_ORDER)
    conn.close()
    logger.info(f"Загружено {len(subscriptions)} подписок")

def save_subscriptions():
    conn = sqlite3.connect(SUBSCRIPTIONS_DB)
    cursor = conn.cursor()
    for user_id, prayers in subscriptions.items():
        prayers_json = json.dumps(list(prayers))
        cursor.execute('INSERT OR REPLACE INTO subscriptions (user_id, prayers) VALUES (?, ?)', (user_id, prayers_json))
    conn.commit()
    conn.close()
    logger.info("Подписки сохранены")

# ==================== РАБОТА С ДАННЫМИ ====================
def load_prayer_data():
    global prayer_data
    try:
        with open(CSV_FILE, 'r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            for row in csv_reader:
                date_str = row['Date'].strip()
                prayer_data[date_str] = {k: v.strip() for k, v in row.items() if k != 'Date'}
        logger.info(f"Загружено {len(prayer_data)} записей о намазах")
        return True
    except Exception as e:
        logger.error(f"Ошибка загрузки CSV: {e}")
        return False

# ==================== КЛАВИАТУРЫ И ИНТЕРФЕЙС ====================
def get_main_menu_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🕐 Сегодня"), KeyboardButton(text="⏩ Завтра"), KeyboardButton(text="🗓️ Месяц")],
            [KeyboardButton(text="🔔 Уведомления"), KeyboardButton(text="🔕 Выкл уведомления")],
            [KeyboardButton(text="ℹ️ Информация"), KeyboardButton(text="🔄 Обновить")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )
    return keyboard

def get_months_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    months_row = []
    for month_num, month_name in MONTHS_RU.items():
        months_row.append(InlineKeyboardButton(text=month_name, callback_data=f"month_{month_num}"))
        if len(months_row) == 3:
            keyboard.inline_keyboard.append(months_row)
            months_row = []
    if months_row:
        keyboard.inline_keyboard.append(months_row)
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")])
    return keyboard

def get_prayer_selection_keyboard(user_id):
    selected = subscriptions.get(user_id, set())
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for prayer in TIME_PRAYER_ORDER:
        text = f"{PRAYER_NAMES[prayer]} {'✅' if prayer in selected else '❌'}"
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=text, callback_data=f"toggle_{prayer}")])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="Сохранить", callback_data="save_prayers")])
    return keyboard

# ==================== УТИЛИТЫ ДЛЯ ФОРМАТИРОВАНИЯ ====================
def get_prayer_times(date_obj=None):
    if date_obj is None:
        date_obj = datetime.now(TIMEZONE)
    date_str = date_obj.strftime("%d.%m")
    return prayer_data.get(date_str, {})

def format_prayer_times(times, date_obj=None):
    if not times:
        return "📭 Данные для этой даты не найдены"
    if date_obj is None:
        date_obj = datetime.now(TIMEZONE)
    month_name_ru = MONTHS_RU.get(date_obj.month, date_obj.strftime("%B"))
    text = f"📅 {date_obj.day:02d} {month_name_ru}\n📍 Черкесск (КЧР)\n\n"
    text += f"🌄 Фаджр:         {times.get('Fajr', '--:--')}\n"
    text += f"Восход:          {times.get('Sunrise', '--:--')}\n"
    text += f"☀️ Зухр:          {times.get('Duhr', '--:--')}\n"
    text += f"🌤 Аср:           {times.get('Asr', '--:--')}\n"
    text += f"🌅 Магриб:        {times.get('Maghrib', '--:--')}\n"
    text += f"🌙 Иша:           {times.get('Isha', '--:--')}\n\n"
    text += f"Треть ночи:      {times.get('FirstThird', '--:--')}\n"
    text += f"Полночь:         {times.get('Midnight', '--:--')}\n"
    text += f"Посл.1/3 ночи:   {times.get('LastThird', '--:--')}\n"
    return text

def format_month_table(times_dict, month_num):
    if not times_dict:
        return "📭 Данные для этого месяца не найдены"
    month_name_ru = MONTHS_RU.get(month_num, f"Месяц {month_num}")
    lines = [f"📅 {month_name_ru}"]
    prayer_names_ru = {p: PRAYER_NAMES[p] for p in PRAYER_ORDER_MONTH}
    header = "День | " + " | ".join(prayer_names_ru[p] for p in PRAYER_ORDER_MONTH)
    lines.append(header)
    lines.append("-" * len(header))
    for date_str, times in sorted(times_dict.items()):
        day = date_str.split('.')[0]
        row = f"{day:>4} | " + " | ".join(times.get(p, '--:--') for p in PRAYER_ORDER_MONTH)
        lines.append(row)
    return "\n".join(lines)

def get_current_prayer_status(times):
    now = datetime.now(TIMEZONE).time()
    current_prayer = "Ночь"
    next_prayer = TIME_PRAYER_ORDER[0]
    time_to_next = None
    for i, prayer in enumerate(TIME_PRAYER_ORDER):
        prayer_time_str = times.get(prayer)
        if not prayer_time_str:
            continue
        prayer_time = datetime.strptime(prayer_time_str, "%H:%M").time()
        if now < prayer_time:
            next_prayer = prayer
            time_to_next = datetime.combine(datetime.today(), prayer_time) - datetime.combine(datetime.today(), now)
            break
        current_prayer = prayer
    if time_to_next:
        hours, remainder = divmod(time_to_next.seconds, 3600)
        minutes = remainder // 60
        status = f"🕌 *Текущий намаз:* {PRAYER_NAMES[current_prayer]}\n⏳ *До следующего ({PRAYER_NAMES[next_prayer]}):* {hours} ч. {minutes} мин."
    else:
        status = f"🕌 *Текущий намаз:* {PRAYER_NAMES[current_prayer]}\n🌙 Следующий день"
    return status

# ==================== УВЕДОМЛЕНИЯ ====================
async def send_prayer_notification(prayer_name: str, prayer_time: str, times: dict, is_reminder=False):
    if not subscriptions:
        logger.info(f"Нет подписчиков для уведомления о {prayer_name}")
        return
    prefix = "Напоминание: " if is_reminder else ""
    message = f"🕌 {prefix}Время намаза: *{prayer_name}*\n⏰ {prayer_time}\n📍 Черкесск (КЧР)\nАссаламу алейкум! Пора на намаз 🌙"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Отметить прочитанным", callback_data="read_notification")]])
    success, failed = 0, 0
    for user_id, user_prayers in list(subscriptions.items()):
        if PRAYER_NAMES.inverse.get(prayer_name, prayer_name) not in user_prayers:  # Проверка на выбранные намазы
            continue
        try:
            await bot.send_message(user_id, message, parse_mode="Markdown", reply_markup=keyboard if not is_reminder else None)
            success += 1
            await asyncio.sleep(0.04)  # Лимит: ~25 сообщений/сек
        except Exception as e:
            logger.error(f"Не удалось отправить {prayer_name} пользователю {user_id}: {e}")
            failed += 1
            if "blocked" in str(e).lower() or "chat not found" in str(e).lower():
                del subscriptions[user_id]
                save_subscriptions()
    logger.info(f"Уведомление {prayer_name} ({'reminder' if is_reminder else 'main'}): отправлено {success}, ошибок {failed}")

def schedule_prayer_notifications():
    scheduler.remove_all_jobs()
    today = datetime.now(TIMEZONE)
    today_str = today.strftime("%d.%m")
    times = prayer_data.get(today_str, {})
    if not times:
        return
    prayers = [(PRAYER_NAMES[p], times[p]) for p in TIME_PRAYER_ORDER if times.get(p)]
    for prayer_name, prayer_time_str in prayers:
        try:
            hour, minute = map(int, prayer_time_str.split(':'))
            prayer_dt = today.replace(hour=hour, minute=minute, second=0, microsecond=0)
            # Основное уведомление
            scheduler.add_job(send_prayer_notification, CronTrigger(hour=hour, minute=minute, timezone=TIMEZONE),
                              args=[prayer_name, prayer_time_str, times, False], id=f"{prayer_name}_{today_str}")
            # Напоминание за 10 мин
            reminder_dt = prayer_dt - timedelta(minutes=10)
            scheduler.add_job(send_prayer_notification, CronTrigger(hour=reminder_dt.hour, minute=reminder_dt.minute, timezone=TIMEZONE),
                              args=[prayer_name, prayer_time_str, times, True], id=f"reminder_{prayer_name}_{today_str}")
            logger.info(f"Запланировано уведомление для {prayer_name} на {prayer_time_str} (и напоминание за 10 мин)")
        except Exception as e:
            logger.error(f"Ошибка планирования {prayer_name}: {e}")

# ==================== КОМАНДЫ И ОБРАБОТЧИКИ БОТА ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in subscriptions:
        subscriptions[user_id] = set(TIME_PRAYER_ORDER)  # Подписка на все по умолчанию
        save_subscriptions()
    welcome_text = (
        "🕌 *Ассаламу алейкум!*\n\n"
        "Я бот с расписанием намазов для Черкесска.\n\n"
        "✅ *Вы автоматически подписаны на все уведомления!*\n"
        "⏰ Уведомления приходят за 10 мин и в точное время\n\n"
        "*Используйте меню внизу: 👇*"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard())

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = (
        "🕌 *Помощь по боту*\n\n"
        "Команды:\n"
        "/start - Запуск и подписка\n"
        "/help - Эта помощь\n\n"
        "Меню:\n"
        "🕐 Сегодня - Расписание на сегодня + статус\n"
        "⏩ Завтра - Расписание на завтра\n"
        "🗓️ Месяц - Выбор месяца\n"
        "🔔 Уведомления - Выбор намазов\n"
        "🔕 Выкл уведомления - Отписка\n"
        "ℹ️ Информация - О боте\n"
        "🔄 Обновить - Перезапуск"
    )
    await message.answer(help_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard())

@dp.message(lambda m: m.text == "🕐 Сегодня")
async def handle_today_button(message: types.Message):
    today = datetime.now(TIMEZONE)
    times = get_prayer_times(today)
    if times:
        await message.answer(format_prayer_times(times, today), reply_markup=get_main_menu_keyboard())
        await message.answer(get_current_prayer_status(times), parse_mode="Markdown", reply_markup=get_main_menu_keyboard())
    else:
        await message.answer("❌ Данные на сегодня не найдены", reply_markup=get_main_menu_keyboard())

@dp.message(lambda m: m.text == "⏩ Завтра")
async def handle_tomorrow_button(message: types.Message):
    tomorrow = datetime.now(TIMEZONE) + timedelta(days=1)
    times = get_prayer_times(tomorrow)
    if times:
        await message.answer(format_prayer_times(times, tomorrow), reply_markup=get_main_menu_keyboard())
    else:
        await message.answer("❌ Данные на завтра не найдены", reply_markup=get_main_menu_keyboard())

@dp.message(lambda m: m.text == "🗓️ Месяц")
async def handle_month_button(message: types.Message):
    await message.answer("📅 *Выберите месяц:*", parse_mode="Markdown", reply_markup=get_months_keyboard())

@dp.message(lambda m: m.text == "🔔 Уведомления")
async def handle_notify_on_button(message: types.Message):
    user_id = message.from_user.id
    if user_id not in subscriptions:
        subscriptions[user_id] = set()
    await message.answer("Выберите намазы для уведомлений:", reply_markup=get_prayer_selection_keyboard(user_id))

@dp.message(lambda m: m.text == "🔕 Выкл уведомления")
async def handle_notify_off_button(message: types.Message):
    user_id = message.from_user.id
    if user_id in subscriptions:
        del subscriptions[user_id]
        save_subscriptions()
    await message.answer("🔕 Уведомления выключены.", reply_markup=get_main_menu_keyboard())

@dp.message(lambda m: m.text == "ℹ️ Информация")
async def handle_info_button(message: types.Message):
    info_text = (
        "🕌 *Расписание намазов для города Черкесска.*\n\n"
        "📍 *Местоположение:* \nЧеркесск (КЧР)\n"
        "🌐 *Координаты:* \n44.22333, 42.05778\n\n"
        "📝 *Хадис:*\n"
        "«Самое лучшее деяние — это намаз, совершенный в начале отведенного для него времени».\n"
        "Этот хадис передали ат-Тирмизи и аль-Хаким.\n\n"
        "Версия: 1.1 (с напоминаниями и выбором)"
    )
    await message.answer(info_text, parse_mode="Markdown", reply_markup=get_main_menu_keyboard())

@dp.message(lambda m: m.text == "🔄 Обновить")
async def handle_refresh_button(message: types.Message):
    await cmd_start(message)

@dp.callback_query()
async def handle_inline_buttons(callback: types.CallbackQuery):
    data = callback.data
    user_id = callback.from_user.id
    if data.startswith("month_"):
        month_num = int(data.split("_")[1])
        month_data = {d: prayer_data[d] for d in prayer_data if d.endswith(f".{month_num:02d}")}
        if month_data:
            await callback.message.edit_text(format_month_table(month_data, month_num))
        else:
            await callback.message.edit_text(f"❌ Данные на {MONTHS_RU.get(month_num)} не найдены")
    elif data == "back_to_menu":
        await callback.message.delete()
        await callback.message.answer("👇 *Используйте меню внизу:*", parse_mode="Markdown", reply_markup=get_main_menu_keyboard())
    elif data.startswith("toggle_"):
        prayer = data.split("_")[1]
        if user_id not in subscriptions:
            subscriptions[user_id] = set()
        if prayer in subscriptions[user_id]:
            subscriptions[user_id].remove(prayer)
        else:
            subscriptions[user_id].add(prayer)
        await callback.message.edit_reply_markup(reply_markup=get_prayer_selection_keyboard(user_id))
    elif data == "save_prayers":
        save_subscriptions()
        await callback.message.edit_text("✅ Настройки уведомлений сохранены!")
    elif data == "read_notification":
        await callback.answer("Прочитано!")
    await callback.answer()

# ==================== ЗАПУСК БОТА ====================
async def on_startup():
    logger.info("🚀 Бот запускается...")
    init_db()
    if not load_prayer_data():
        logger.critical("Не удалось загрузить данные CSV!")
        return
    load_subscriptions()
    schedule_prayer_notifications()
    scheduler.start()
    scheduler.add_job(schedule_prayer_notifications, CronTrigger(hour=0, minute=1, timezone=TIMEZONE), id="daily_schedule_update")
    logger.info("✅ Бот успешно запущен!")

async def main():
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

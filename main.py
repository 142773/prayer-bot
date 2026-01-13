import asyncio
import os
import csv
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import pytz

# ==================== ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ====================
load_dotenv()  # Загружает переменные из .env файла

# ==================== НАСТРОЙКИ ====================
API_TOKEN = os.getenv('API_TOKEN')  # Токен теперь берется из .env файла
CSV_FILE = 'prayer_times_cherkessk.csv'
SUBSCRIPTIONS_FILE = 'subscriptions.json'
TIMEZONE = pytz.timezone('Europe/Moscow')

# Русские названия месяцев
MONTHS_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

# ==================== КОЛБЭК ДАННЫЕ ====================
class PrayerCallback(CallbackData, prefix="prayer"):
    action: str

# ==================== РАБОТА С ДАННЫМИ ====================
prayer_data = {}
subscribed_users = set()

def load_prayer_data():
    """Загружает данные из CSV файла"""
    global prayer_data
    
    try:
        with open(CSV_FILE, 'r', encoding='utf-8') as file:
            csv_reader = csv.DictReader(file)
            
            for row in csv_reader:
                date_str = row['Date'].strip()
                prayer_data[date_str] = {
                    'Fajr': row['Fajr'].strip(),
                    'Sunrise': row['Sunrise'].strip(),
                    'Duhr': row['Duhr'].strip(),
                    'Asr': row['Asr'].strip(),
                    'Maghrib': row['Maghrib'].strip(),
                    'Isha': row['Isha'].strip(),
                    'FirstThird': row['FirstThird'].strip(),
                    'Midnight': row['Midnight'].strip(),
                    'LastThird': row['LastThird'].strip()
                }
                
        print(f"✅ Загружено {len(prayer_data)} записей о намазах")
        return True
    except Exception as e:
        print(f"❌ Ошибка загрузки CSV: {e}")
        return False

def load_subscriptions():
    """Загружает подписки из файла"""
    global subscribed_users
    
    try:
        if os.path.exists(SUBSCRIPTIONS_FILE):
            with open(SUBSCRIPTIONS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                subscribed_users = set(data.get('users', []))
                print(f"✅ Загружено {len(subscribed_users)} подписок")
    except Exception as e:
        print(f"❌ Ошибка загрузки подписок: {e}")
        subscribed_users = set()

def save_subscriptions():
    """Сохраняет подписки в файл"""
    try:
        data = {'users': list(subscribed_users)}
        with open(SUBSCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("✅ Подписки сохранены")
    except Exception as e:
        print(f"❌ Ошибка сохранения подписок: {e}")

# ==================== КЛАВИАТУРЫ ====================
def get_main_keyboard():
    """Основная клавиатура с кнопками"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Сегодня", callback_data=PrayerCallback(action="today").pack()),
            InlineKeyboardButton(text="⏩ Завтра", callback_data=PrayerCallback(action="tomorrow").pack())
        ],
        [
            InlineKeyboardButton(text="📊 Месяц", callback_data=PrayerCallback(action="month").pack()),
            InlineKeyboardButton(text="📈 След. месяц", callback_data=PrayerCallback(action="nextmonth").pack())
        ],
        [
            InlineKeyboardButton(text="🔔 Вкл уведомления", callback_data=PrayerCallback(action="notify_on").pack()),
            InlineKeyboardButton(text="🔕 Выкл уведомления", callback_data=PrayerCallback(action="notify_off").pack())
        ],
        [
            InlineKeyboardButton(text="ℹ️ Информация", callback_data=PrayerCallback(action="info").pack())
        ]
    ])
    return keyboard

# ==================== УТИЛИТЫ ====================
def get_prayer_times(date_obj=None):
    """Возвращает время намазов для указанной даты"""
    if date_obj is None:
        date_obj = datetime.now(TIMEZONE)
    
    date_str = date_obj.strftime("%d.%m")
    return prayer_data.get(date_str, {})

def format_prayer_times(times, date_obj=None):
    """Форматирует время намазов для вывода"""
    if not times:
        return "📭 Данные для этой даты не найдены"
    
    if date_obj is None:
        date_obj = datetime.now(TIMEZONE)
    
    formatted = f"🕌 *Расписание намазов*\n"
    formatted += f"📅 {date_obj.strftime('%d %B %Y')}\n"
    formatted += f"📍 Черкесск (КЧР)\n\n"
    
    prayers = [
        ("🌄 *Фаджр*", times.get('Fajr', '--:--'), f"Восход: {times.get('Sunrise', '--:--')}"),
        ("☀️ *Зухр*", times.get('Duhr', '--:--'), ""),
        ("🌤 *Аср*", times.get('Asr', '--:--'), ""),
        ("🌅 *Магриб*", times.get('Maghrib', '--:--'), ""),
        ("🌙 *Иша*", times.get('Isha', '--:--'), 
         f"1-я треть: {times.get('FirstThird', '--:--')}\n"
         f"Полночь: {times.get('Midnight', '--:--')}\n"
         f"Последняя треть: {times.get('LastThird', '--:--')}")
    ]
    
    for name, time, extra in prayers:
        formatted += f"{name}: `{time}`\n"
        if extra:
            formatted += f"{extra}\n"
    
    return formatted

def format_month_prayer_times(times, day, month_name_ru):
    """Форматирует время намазов для вывода в месяце"""
    if not times:
        return f"*{day:02d} {month_name_ru}*: Нет данных"
    
    return (f"*{day:02d} {month_name_ru}*: "
            f"Фаджр `{times.get('Fajr', '--:--')}`, "
            f"Восх `{times.get('Sunrise', '--:--')}`, "
            f"Зухр `{times.get('Duhr', '--:--')}`, "
            f"Аср `{times.get('Asr', '--:--')}`, "
            f"Магриб `{times.get('Maghrib', '--:--')}`, "
            f"Иша `{times.get('Isha', '--:--')}`")

# ==================== СИСТЕМА УВЕДОМЛЕНИЙ ====================
async def send_prayer_notification(prayer_name, prayer_time_str, prayer_data_today):
    """Отправляет уведомление о намазе"""
    
    notification_text = ""
    
    if prayer_name == "Фаджр":
        sunrise = prayer_data_today.get('Sunrise', '--:--')
        notification_text = (
            f"🕌 *Время намаза!*\n\n"
            f"🌄 *{prayer_name}* в `{prayer_time_str}`\n\n"
            f"📌 *Восход солнца:* `{sunrise}`\n"
            f"Не пропустите утренний намаз!"
        )
    
    elif prayer_name == "Иша":
        first_third = prayer_data_today.get('FirstThird', '--:--')
        midnight = prayer_data_today.get('Midnight', '--:--')
        last_third = prayer_data_today.get('LastThird', '--:--')
        notification_text = (
            f"🕌 *Время намаза!*\n\n"
            f"🌙 *{prayer_name}* в `{prayer_time_str}`\n\n"
            f"🌜 *Времена ночи:*\n"
            f"• 1-я треть: `{first_third}`\n"
            f"• Полночь: `{midnight}`\n"
            f"• Последняя треть: `{last_third}`\n\n"
            f"Используйте это время для тахаджуд намаза!"
        )
    
    else:
        notification_text = (
            f"🕌 *Время намаза!*\n\n"
            f"*{prayer_name}* в `{prayer_time_str}`\n\n"
            f"Не пропустите намаз!"
        )
    
    for user_id in subscribed_users:
        try:
            await bot.send_message(user_id, notification_text, parse_mode="Markdown")
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

def schedule_prayer_notifications():
    """Планирует уведомления на сегодня"""
    scheduler.remove_all_jobs()
    
    today = datetime.now(TIMEZONE)
    today_str = today.strftime("%d.%m")
    times = prayer_data.get(today_str, {})
    
    if not times:
        return
    
    prayers = [
        ("Фаджр", times['Fajr']),
        ("Зухр", times['Duhr']),
        ("Аср", times['Asr']),
        ("Магриб", times['Maghrib']),
        ("Иша", times['Isha'])
    ]
    
    for prayer_name, prayer_time_str in prayers:
        try:
            prayer_hour, prayer_minute = map(int, prayer_time_str.split(':'))
            prayer_datetime = today.replace(
                hour=prayer_hour, 
                minute=prayer_minute, 
                second=0, 
                microsecond=0
            )
            
            # Уведомление в ТОЧНОЕ время намаза
            scheduler.add_job(
                send_prayer_notification,
                CronTrigger(
                    hour=prayer_datetime.hour,
                    minute=prayer_datetime.minute,
                    timezone=TIMEZONE
                ),
                args=[prayer_name, prayer_time_str, times],
                id=f"{prayer_name}_{today_str}"
            )
            
            print(f"⏰ Запланировано уведомление для {prayer_name} на {prayer_time_str}")
            
        except Exception as e:
            print(f"❌ Ошибка планирования {prayer_name}: {e}")

# ==================== КОМАНДЫ БОТА ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Команда /start"""
    welcome_text = (
        "🕌 *Ассаламу алейкум!*\n\n"
        "Я бот с расписанием намазов для Черкесска.\n\n"
        "📋 *Используйте кнопки ниже или команды:*\n"
        "`/today` - расписание на сегодня\n"
        "`/tomorrow` - на завтра\n"
        "`/month` - на месяц\n"
        "`/notify on` - включить уведомления\n"
        "`/notify off` - выключить уведомления\n\n"
        "⏰ *Уведомления приходят в точное время намазов!*"
    )
    
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@dp.message(Command("today"))
async def cmd_today(message: types.Message):
    """Расписание на сегодня"""
    today = datetime.now(TIMEZONE)
    times = get_prayer_times(today)
    
    if times:
        response = format_prayer_times(times, today)
        await message.answer(response, parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await message.answer("❌ Данные на сегодня не найдены")

@dp.message(Command("tomorrow"))
async def cmd_tomorrow(message: types.Message):
    tomorrow = datetime.now(TIMEZONE) + timedelta(days=1)
    times = get_prayer_times(tomorrow)
    
    if times:
        response = format_prayer_times(times, tomorrow)
        await message.answer(response, parse_mode="Markdown", reply_markup=get_main_keyboard())
    else:
        await message.answer("❌ Данные на завтра не найдены")

@dp.message(Command("month"))
async def cmd_month(message: types.Message):
    """Расписание на месяц"""
    now = datetime.now(TIMEZONE)
    month_name_ru = MONTHS_RU.get(now.month, now.strftime("%B"))
    month_data = []
    
    for day in range(1, 32):
        date_str = f"{day:02d}.{now.month:02d}"
        if date_str in prayer_data:
            times = prayer_data[date_str]
            month_data.append(format_month_prayer_times(times, day, month_name_ru))
    
    if month_data:
        # Разбиваем на части по 10 дней, чтобы не превысить лимит Telegram
        chunks = [month_data[i:i+10] for i in range(0, len(month_data), 10)]
        
        for i, chunk in enumerate(chunks):
            part_text = f" (Часть {i+1}/{len(chunks)})" if len(chunks) > 1 else ""
            response = f"📅 *Расписание на {month_name_ru} {now.year}{part_text}*\n\n" + "\n".join(chunk)
            await message.answer(response, parse_mode="Markdown", 
                                 reply_markup=get_main_keyboard() if i == len(chunks)-1 else None)
    else:
        await message.answer("❌ Данные на этот месяц не найдены")

@dp.message(Command("notify"))
async def cmd_notify(message: types.Message):
    """Управление уведомлениями"""
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer(
            "Используйте:\n"
            "`/notify on` - включить уведомления\n"
            "`/notify off` - выключить уведомления",
            reply_markup=get_main_keyboard()
        )
        return
    
    action = args[1].lower()
    
    if action == "on":
        subscribed_users.add(user_id)
        save_subscriptions()
        await message.answer("✅ Уведомления включены! Вы будете получать напоминания в точное время намазов.", reply_markup=get_main_keyboard())
    elif action == "off":
        if user_id in subscribed_users:
            subscribed_users.remove(user_id)
            save_subscriptions()
        await message.answer("🔕 Уведомления выключены.", reply_markup=get_main_keyboard())

# ==================== ОБРАБОТКА КНОПОК ====================
@dp.callback_query(PrayerCallback.filter())
async def handle_callback(query: types.CallbackQuery, callback_data: PrayerCallback):
    """Обработка нажатий кнопок"""
    user_id = query.from_user.id
    action = callback_data.action
    
    if action == "today":
        today = datetime.now(TIMEZONE)
        times = get_prayer_times(today)
        if times:
            response = format_prayer_times(times, today)
            await query.message.edit_text(response, parse_mode="Markdown", reply_markup=get_main_keyboard())
    
    elif action == "tomorrow":
        tomorrow = datetime.now(TIMEZONE) + timedelta(days=1)
        times = get_prayer_times(tomorrow)
        if times:
            response = format_prayer_times(times, tomorrow)
            await query.message.edit_text(response, parse_mode="Markdown", reply_markup=get_main_keyboard())
    
    elif action == "month":
        now = datetime.now(TIMEZONE)
        month_name_ru = MONTHS_RU.get(now.month, now.strftime("%B"))
        month_data = []
        
        for day in range(1, 32):
            date_str = f"{day:02d}.{now.month:02d}"
            if date_str in prayer_data:
                times = prayer_data[date_str]
                month_data.append(format_month_prayer_times(times, day, month_name_ru))
        
        if month_data:
            # Разбиваем на части по 10 дней
            chunks = [month_data[i:i+10] for i in range(0, len(month_data), 10)]
            chunk = chunks[0]  # Для inline кнопок показываем только первую часть
            response = f"📅 *Расписание на {month_name_ru} {now.year}*\n\n" + "\n".join(chunk)
            
            # Добавляем кнопки для навигации если частей больше одной
            keyboard = get_main_keyboard()
            if len(chunks) > 1:
                # Можно добавить дополнительные кнопки для навигации по частям
                pass
                
            await query.message.edit_text(response, parse_mode="Markdown", reply_markup=keyboard)
    
    elif action == "nextmonth":
        next_month = datetime.now(TIMEZONE) + timedelta(days=32)
        next_month = next_month.replace(day=1)
        month_name_ru = MONTHS_RU.get(next_month.month, next_month.strftime("%B"))
        month_data = []
        
        for day in range(1, 32):
            date_str = f"{day:02d}.{next_month.month:02d}"
            if date_str in prayer_data:
                times = prayer_data[date_str]
                month_data.append(format_month_prayer_times(times, day, month_name_ru))
        
        if month_data:
            # Разбиваем на части по 10 дней
            chunks = [month_data[i:i+10] for i in range(0, len(month_data), 10)]
            chunk = chunks[0]  # Для inline кнопок показываем только первую часть
            response = f"📅 *Расписание на {month_name_ru} {next_month.year}*\n\n" + "\n".join(chunk)
            await query.message.edit_text(response, parse_mode="Markdown", reply_markup=get_main_keyboard())
    
    elif action == "notify_on":
        subscribed_users.add(user_id)
        save_subscriptions()
        await query.message.edit_text(
            "✅ Уведомления включены!\nВы будете получать напоминания в точное время намазов.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    
    elif action == "notify_off":
        if user_id in subscribed_users:
            subscribed_users.remove(user_id)
            save_subscriptions()
        await query.message.edit_text(
            "🔕 Уведомления выключены.",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    
    elif action == "info":
        info_text = (
            "🕌 *Информация о боте*\n\n"
            "📍 *Местоположение:* Черкесск (КЧР)\n"
            "🌐 *Координаты:* 44.22333, 42.05778\n"
            "📊 *Данные:* 2026 год\n"
            "👤 *Составитель:* Muslims of the KCHR Region\n"
            "📅 *Обновлено:* 10.01.2026\n\n"
            "📞 *Контакты:* 142773@gmail.com\n"
            "📝 *Примечание:* Allahu Akbar"
        )
        await query.message.edit_text(info_text, parse_mode="Markdown", reply_markup=get_main_keyboard())
    
    await query.answer()

# ==================== ЗАПУСК БОТА ====================
async def on_startup():
    """Действия при запуске бота"""
    print("🚀 Бот запускается...")
    
    # Загружаем данные
    if not load_prayer_data():
        print("❌ Критическая ошибка: не удалось загрузить данные CSV!")
        return
    
    # Загружаем подписки
    load_subscriptions()
    
    # Планируем уведомления
    schedule_prayer_notifications()
    
    # Запускаем планировщик
    scheduler.start()
    
    # Обновляем расписание каждый день в 00:01
    scheduler.add_job(
        schedule_prayer_notifications,
        CronTrigger(hour=0, minute=1, timezone=TIMEZONE),
        id="daily_schedule_update"
    )
    
    # Сохраняем подписки каждые 30 минут
    scheduler.add_job(
        save_subscriptions,
        CronTrigger(minute="*/30", timezone=TIMEZONE),
        id="save_subscriptions"
    )
    
    print("✅ Бот успешно запущен!")

async def main():
    """Основная функция"""
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

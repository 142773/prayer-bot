import asyncio
import os
import csv
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# ==================== НАСТРОЙКИ ====================
API_TOKEN = os.getenv('API_TOKEN', '1770216492:AAEwIm93NcD-IKA2wYk5qTzUMERpHcJbtgE')
CSV_FILE = 'pac_cher_bot.csv'
TIMEZONE = pytz.timezone('Europe/Moscow')  # Часовой пояс Черкесска

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

# ==================== РАБОТА С CSV ====================
prayer_data = {}
location_info = {}

def load_prayer_data():
    """Загружает данные из CSV файла"""
    global prayer_data, location_info
    
    try:
        with open(CSV_FILE, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            
            # Читаем информацию о местоположении
            for i in range(7):
                if i < len(lines):
                    line = lines[i].strip()
                    if ':' in line:
                        key, value = line.split(':', 1)
                        location_info[key.strip()] = value.strip()
            
            # Читаем расписания намазов
            csv_reader = csv.DictReader(lines[7:])
            for row in csv_reader:
                month = row['Month'].strip()
                date = int(row['Date'].strip())
                key = f"{month},{date}"
                
                prayer_data[key] = {
                    'Fajr': row['Fajr'].strip(),
                    'Sunrise': row['Sunrise'].strip(),
                    'Duhr': row['Duhr'].strip(),
                    'Asr': row['Asr'].strip(),
                    'Maghrib': row['Maghrib'].strip(),
                    'Isha': row['Isha'].strip()
                }
                
        print(f"Загружено {len(prayer_data)} записей о намазах")
        return True
    except Exception as e:
        print(f"Ошибка загрузки CSV: {e}")
        return False

def get_prayer_times(date_obj=None):
    """Возвращает время намазов для указанной даты"""
    if date_obj is None:
        date_obj = datetime.now(TIMEZONE)
    
    month = date_obj.strftime("%B")
    date = date_obj.day
    
    key = f"{month},{date}"
    return prayer_data.get(key, {})

def format_prayer_times(times, date_obj=None):
    """Форматирует время намазов для вывода"""
    if not times:
        return "Данные для этой даты не найдены"
    
    if date_obj is None:
        date_obj = datetime.now(TIMEZONE)
    
    formatted = f"📅 *{date_obj.strftime('%d %B %Y')}*\n"
    formatted += f"📍 {location_info.get('Location', 'Черкесск')}\n\n"
    
    prayers = [
        ("🌄 Фаджр", times.get('Fajr', '--:--')),
        ("☀️ Восход", times.get('Sunrise', '--:--')),
        ("☀️ Зухр", times.get('Duhr', '--:--')),
        ("🌤 Аср", times.get('Asr', '--:--')),
        ("🌅 Магриб", times.get('Maghrib', '--:--')),
        ("🌙 Иша", times.get('Isha', '--:--'))
    ]
    
    for name, time in prayers:
        formatted += f"{name}: `{time}`\n"
    
    return formatted

# ==================== КОМАНДЫ БОТА ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Команда /start"""
    welcome_text = (
        "🕌 *Ассаламу алейкум!*\n\n"
        "Я бот с расписанием намазов для Черкесска.\n\n"
        "📋 *Доступные команды:*\n"
        "`/today` - расписание на сегодня\n"
        "`/tomorrow` - расписание на завтра\n"
        "`/month` - расписание на текущий месяц\n"
        "`/nextmonth` - расписание на следующий месяц\n"
        "`/notify on` - включить уведомления\n"
        "`/notify off` - выключить уведомления\n"
        "`/info` - информация о боте\n\n"
        "⏰ Уведомления будут приходить за 5 минут до каждого намаза."
    )
    
    await message.answer(welcome_text, parse_mode="Markdown")

@dp.message(Command("today"))
async def cmd_today(message: types.Message):
    """Расписание на сегодня"""
    today = datetime.now(TIMEZONE)
    times = get_prayer_times(today)
    
    if times:
        response = format_prayer_times(times, today)
        await message.answer(response, parse_mode="Markdown")
    else:
        await message.answer("❌ Данные на сегодня не найдены")

@dp.message(Command("tomorrow"))
async def cmd_tomorrow(message: types.Message):
    """Расписание на завтра"""
    tomorrow = datetime.now(TIMEZONE) + timedelta(days=1)
    times = get_prayer_times(tomorrow)
    
    if times:
        response = format_prayer_times(times, tomorrow)
        await message.answer(response, parse_mode="Markdown")
    else:
        await message.answer("❌ Данные на завтра не найдены")

@dp.message(Command("month"))
async def cmd_month(message: types.Message):
    """Расписание на текущий месяц"""
    now = datetime.now(TIMEZONE)
    current_month = now.month
    current_year = now.year
    
    response = f"📅 *Расписание на {now.strftime('%B %Y')}*\n\n"
    
    # Находим все записи для текущего месяца
    month_name = now.strftime("%B")
    month_data = []
    
    for day in range(1, 32):
        key = f"{month_name},{day}"
        if key in prayer_data:
            times = prayer_data[key]
            date_str = f"{day:02d} {month_name}"
            month_data.append(f"*{date_str}*: Фаджр `{times['Fajr']}`, Зухр `{times['Duhr']}`, Магриб `{times['Maghrib']}`")
    
    if month_data:
        # Разбиваем на части, если слишком длинное сообщение
        for i in range(0, len(month_data), 10):
            part = "\n".join(month_data[i:i+10])
            await message.answer(part, parse_mode="Markdown")
    else:
        await message.answer("❌ Данные на этот месяц не найдены")

@dp.message(Command("nextmonth"))
async def cmd_nextmonth(message: types.Message):
    """Расписание на следующий месяц"""
    now = datetime.now(TIMEZONE)
    next_month_date = now + timedelta(days=32)
    next_month_date = next_month_date.replace(day=1)
    next_month = next_month_date.month
    next_year = next_month_date.year
    
    response = f"📅 *Расписание на {next_month_date.strftime('%B %Y')}*\n\n"
    
    # Находим все записи для следующего месяца
    month_name = next_month_date.strftime("%B")
    month_data = []
    
    for day in range(1, 32):
        key = f"{month_name},{day}"
        if key in prayer_data:
            times = prayer_data[key]
            date_str = f"{day:02d} {month_name}"
            month_data.append(f"*{date_str}*: Фаджр `{times['Fajr']}`, Зухр `{times['Duhr']}`, Магриб `{times['Maghrib']}`")
    
    if month_data:
        for i in range(0, len(month_data), 10):
            part = "\n".join(month_data[i:i+10])
            await message.answer(part, parse_mode="Markdown")
    else:
        await message.answer("❌ Данные на следующий месяц не найдены")

@dp.message(Command("info"))
async def cmd_info(message: types.Message):
    """Информация о боте"""
    info_text = (
        f"🕌 *Информация о расписании*\n\n"
        f"📍 *Местоположение:* {location_info.get('Location', 'Не указано')}\n"
        f"🌐 *Координаты:* {location_info.get('Latitude', '?')}, {location_info.get('Longitude', '?')}\n"
        f"📊 *Загружено записей:* {len(prayer_data)}\n"
        f"👤 *Составитель:* {location_info.get('Compiled By', 'Не указано')}\n"
        f"📅 *Актуальность:* {location_info.get('Contributed By', 'Не указано')}\n\n"
        f"📞 *Поддержка:* {location_info.get('Website', 'Не указано')}\n"
        f"📝 *Примечание:* {location_info.get('Notes', '')}"
    )
    
    await message.answer(info_text, parse_mode="Markdown")

# ==================== СИСТЕМА УВЕДОМЛЕНИЙ ====================
subscribed_users = set()

async def send_prayer_notification(prayer_name, prayer_time):
    """Отправляет уведомление о намазе всем подписанным пользователям"""
    notification_text = f"🕌 *Время намаза!*\n\n{prayer_name} в `{prayer_time}`\n\nНе пропустите намаз!"
    
    for user_id in subscribed_users:
        try:
            await bot.send_message(user_id, notification_text, parse_mode="Markdown")
        except Exception as e:
            print(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

def schedule_prayer_notifications():
    """Планирует уведомления на сегодня"""
    # Удаляем старые задачи
    scheduler.remove_all_jobs()
    
    today = datetime.now(TIMEZONE)
    times = get_prayer_times(today)
    
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
            # Преобразуем время строки в объект datetime на сегодня
            prayer_hour, prayer_minute = map(int, prayer_time_str.split(':'))
            prayer_datetime = today.replace(
                hour=prayer_hour, 
                minute=prayer_minute, 
                second=0, 
                microsecond=0
            )
            
            # Время уведомления (за 5 минут до намаза)
            notify_time = prayer_datetime - timedelta(minutes=5)
            
            # Если время уведомления уже прошло сегодня, пропускаем
            if notify_time < today:
                continue
            
            # Создаем cron триггер
            scheduler.add_job(
                send_prayer_notification,
                CronTrigger(
                    hour=notify_time.hour,
                    minute=notify_time.minute,
                    timezone=TIMEZONE
                ),
                args=[prayer_name, prayer_time_str],
                id=f"{prayer_name}_{today.strftime('%Y%m%d')}"
            )
            
            print(f"Запланировано уведомление для {prayer_name} на {notify_time.strftime('%H:%M')}")
            
        except Exception as e:
            print(f"Ошибка планирования {prayer_name}: {e}")

@dp.message(Command("notify"))
async def cmd_notify(message: types.Message):
    """Управление уведомлениями"""
    user_id = message.from_user.id
    args = message.text.split()
    
    if len(args) < 2:
        await message.answer(
            "Используйте:\n"
            "`/notify on` - включить уведомления\n"
            "`/notify off` - выключить уведомления"
        )
        return
    
    action = args[1].lower()
    
    if action == "on":
        subscribed_users.add(user_id)
        await message.answer("✅ Уведомления включены! Вы будете получать напоминания за 5 минут до каждого намаза.")
    elif action == "off":
        if user_id in subscribed_users:
            subscribed_users.remove(user_id)
        await message.answer("🔕 Уведомления выключены.")
    else:
        await message.answer("❌ Неизвестная команда. Используйте `on` или `off`")

# ==================== ЗАПУСК БОТА ====================
async def on_startup():
    """Действия при запуске бота"""
    print("Бот запускается...")
    
    # Загружаем данные
    if not load_prayer_data():
        print("Критическая ошибка: не удалось загрузить данные CSV!")
        return
    
    # Планируем уведомления
    schedule_prayer_notifications()
    
    # Запускаем планировщик
    scheduler.start()
    
    # Планируем обновление уведомлений каждый день в полночь
    scheduler.add_job(
        schedule_prayer_notifications,
        CronTrigger(hour=0, minute=1, timezone=TIMEZONE),
        id="daily_schedule_update"
    )
    
    print("Бот успешно запущен!")

async def main():
    """Основная функция"""
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
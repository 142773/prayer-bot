"""
Бот для расписания намазов в Черкесске (КЧР)
Версия 2.0 - с исправленными уведомлениями и выравниванием
"""

import asyncio
import os
import csv
import json
from datetime import datetime, timedelta

# Импорты для Telegram бота
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Импорты для планировщика уведомлений
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Импорты для конфигурации
from dotenv import load_dotenv
import pytz

# ==================== ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ====================
try:
    load_dotenv()  # Загружаем переменные из файла .env
except:
    print("⚠️ .env файл не найден, используем системные переменные")

# ==================== НАСТРОЙКИ И КОНФИГУРАЦИЯ ====================
# Получаем токен бота из переменных окружения
API_TOKEN = os.getenv('API_TOKEN') or os.environ.get('API_TOKEN')

# Проверяем, что токен был найден
if not API_TOKEN:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: Не найден API_TOKEN!")
    print("✅ На bothost.ru добавьте переменную окружения: API_TOKEN=ваш_токен")
    exit(1)

# Названия файлов с данными
CSV_FILE = 'prayer_times_cherkessk.csv'
SUBSCRIPTIONS_FILE = 'subscriptions.json'

# Устанавливаем часовой пояс (Москва для Черкесска)
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

# Порядок намазов для вывода месяца (без восхода солнца)
PRAYER_ORDER_MONTH = ['Fajr', 'Duhr', 'Asr', 'Maghrib', 'Isha']

# Порядок намазов для детального вывода (день)
DETAILED_PRAYER_ORDER = ['Fajr', 'Sunrise', 'Duhr', 'Asr', 'Maghrib', 'Isha', 'FirstThird', 'Midnight', 'LastThird']

# Порядок намазов для временного расчета
TIME_PRAYER_ORDER = ['Fajr', 'Duhr', 'Asr', 'Maghrib', 'Isha']

# ==================== ИНИЦИАЛИЗАЦИЯ КОМПОНЕНТОВ ====================
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

# ==================== РАБОТА С ДАННЫМИ ====================
prayer_data = {}
subscribed_users = set()

def load_prayer_data():
    """Загружает данные о времени намазов из CSV файла"""
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
    """Загружает список подписанных пользователей из JSON файла"""
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
    """Сохраняет список подписанных пользователей в JSON файл"""
    try:
        data = {'users': list(subscribed_users)}
        with open(SUBSCRIPTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("✅ Подписки сохранены")
    except Exception as e:
        print(f"❌ Ошибка сохранения подписок: {e}")

def log_notification_status():
    """Логирует статус уведомлений для отладки"""
    today = datetime.now(TIMEZONE)
    today_str = today.strftime("%d.%m")
    times = prayer_data.get(today_str, {})
    
    print(f"\n🔔 СТАТУС УВЕДОМЛЕНИЙ:")
    print(f"📅 Дата: {today_str}")
    print(f"🕐 Текущее время: {today.strftime('%H:%M:%S')}")
    print(f"👥 Подписанных пользователей: {len(subscribed_users)}")
    
    if times:
        print("✅ Данные на сегодня найдены:")
        for prayer in ['Fajr', 'Duhr', 'Asr', 'Maghrib', 'Isha']:
            if prayer in times:
                print(f"   {prayer}: {times[prayer]}")
    else:
        print("❌ Нет данных на сегодня")
    
    # Показываем запланированные задания
    jobs = scheduler.get_jobs()
    print(f"\n📋 Запланировано заданий: {len(jobs)}")
    for job in jobs:
        next_run = job.next_run_time.astimezone(TIMEZONE) if job.next_run_time else "Не запланировано"
        print(f"   - {job.id}: {next_run}")

# ==================== КЛАВИАТУРЫ И ИНТЕРФЕЙС ====================
def get_main_menu_keyboard():
    """Создает основное меню бота (кнопки внизу экрана)"""
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=[
            [
                types.KeyboardButton(text="🕐 Сегодня"),
                types.KeyboardButton(text="⏩ Завтра"),
                types.KeyboardButton(text="🗓️ Месяц")
            ],
            [
                types.KeyboardButton(text="🔔 Вкл уведомления"),
                types.KeyboardButton(text="🔕 Выкл уведомления")
            ],
            [
                types.KeyboardButton(text="📊 Статус"),
                types.KeyboardButton(text="ℹ️ Информация"),
                types.KeyboardButton(text="🔄 Обновить")
            ]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )
    return keyboard

def get_months_keyboard():
    """Создает inline-клавиатуру с выбором месяца"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    months_row = []
    for month_num, month_name in MONTHS_RU.items():
        months_row.append(
            InlineKeyboardButton(text=month_name, callback_data=f"month_{month_num}")
        )
        if len(months_row) == 3:
            keyboard.inline_keyboard.append(months_row)
            months_row = []
    
    if months_row:
        keyboard.inline_keyboard.append(months_row)
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")
    ])
    
    return keyboard

# ==================== УТИЛИТЫ ДЛЯ ФОРМАТИРОВАНИЯ ====================
def get_prayer_times(date_obj=None):
    """Получает время намазов для указанной даты"""
    if date_obj is None:
        date_obj = datetime.now(TIMEZONE)
    
    date_str = date_obj.strftime("%d.%m")
    return prayer_data.get(date_str, {})

def format_prayer_times(times, date_obj=None):
    """Форматирует время намазов с точным выравниванием"""
    if not times:
        return "📭 Данные для этой даты не найдены"
    
    if date_obj is None:
        date_obj = datetime.now(TIMEZONE)
    
    month_name_ru = MONTHS_RU.get(date_obj.month, date_obj.strftime("%B"))
    
    # Заголовок
    text = f"📅 {date_obj.day:02d} {month_name_ru}\n"
    text += f"📍 Черкесск (КЧР)\n\n"
    
    # Основные намазы с ручным выравниванием для идеального результата
    text += f"🌄 Фаджр:         {times.get('Fajr', '--:--')}\n"
    text += f"Восход:          {times.get('Sunrise', '--:--')}\n"
    text += f"☀️ Зухр:          {times.get('Duhr', '--:--')}\n"
    text += f"🌤 Аср:           {times.get('Asr', '--:--')}\n"
    text += f"🌅 Магриб:        {times.get('Maghrib', '--:--')}\n"
    text += f"🌙 Иша:           {times.get('Isha', '--:--')}\n"
    
    text += "\n"
    
    # Ночные времена
    text += f"Треть ночи:      {times.get('FirstThird', '--:--')}\n"
    text += f"Полночь:         {times.get('Midnight', '--:--')}\n"
    text += f"Посл.1/3 ночи:   {times.get('LastThird', '--:--')}\n"
    
    return text

def format_month_table(times_dict, month_num):
    """Форматирует время намазов для вывода в виде таблицы на месяц"""
    if not times_dict:
        return "📭 Данные для этого месяца не найдены"
    
    month_name_ru = MONTHS_RU.get(month_num, f"Месяц {month_num}")
    
    lines = [f"📅 {month_name_ru}"]
    
    # Добавляем заголовки таблицы
    prayer_names_ru = {
        'Fajr': 'Фаджр',
        'Duhr': 'Зухр', 
        'Asr': 'Аср',
        'Maghrib': 'Магриб',
        'Isha': 'Иша'
    }
    
    header_parts = []
    for prayer in PRAYER_ORDER_MONTH:
        if prayer in prayer_names_ru:
            header_parts.append(prayer_names_ru[prayer])
    
    if header_parts:
        lines.append(" ".join(header_parts))
    
    # Добавляем данные для каждого дня
    for day in range(1, 32):
        date_str = f"{day:02d}.{month_num:02d}"
        if date_str in times_dict:
            times = times_dict[date_str]
            
            time_parts = []
            for prayer in PRAYER_ORDER_MONTH:
                if prayer in times:
                    time_parts.append(times[prayer])
                else:
                    time_parts.append("--:--")
            
            time_str = " ".join(time_parts)
            day_line = f"{day:02d}. {time_str}"
            lines.append(day_line)
    
    if len(lines) <= 2:
        return f"❌ Нет данных для {month_name_ru}"
    
    return "\n".join(lines)

def get_current_prayer_status(times):
    """Определяет статус текущего намаза: сколько прошло и сколько осталось"""
    now = datetime.now(TIMEZONE)
    current_time = now.time()
    
    prayer_times = []
    for prayer in TIME_PRAYER_ORDER:
        if prayer in times and times[prayer] != '--:--':
            try:
                hour, minute = map(int, times[prayer].split(':'))
                prayer_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                prayer_times.append((prayer, prayer_time))
            except:
                continue
    
    if not prayer_times:
        return "⏰ Нет данных о времени намазов"
    
    previous_prayer = None
    next_prayer = None
    
    for prayer, prayer_time in prayer_times:
        if prayer_time.time() <= current_time:
            previous_prayer = (prayer, prayer_time)
        elif prayer_time.time() > current_time and next_prayer is None:
            next_prayer = (prayer, prayer_time)
    
    if previous_prayer and previous_prayer[0] == 'Isha':
        next_day = now + timedelta(days=1)
        next_day_str = next_day.strftime("%d.%m")
        next_day_times = prayer_data.get(next_day_str, {})
        
        if 'Fajr' in next_day_times and next_day_times['Fajr'] != '--:--':
            try:
                hour, minute = map(int, next_day_times['Fajr'].split(':'))
                next_fajr = next_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
                next_prayer = ('Fajr', next_fajr)
            except:
                pass
    
    status_text = "⏳ *Текущий статус:*\n\n"
    
    if previous_prayer:
        prayer_name_ru = PRAYER_NAMES.get(previous_prayer[0], previous_prayer[0])
        time_passed = now - previous_prayer[1]
        hours_passed = time_passed.seconds // 3600
        minutes_passed = (time_passed.seconds % 3600) // 60
        
        status_text += f"📌 *Прошлый намаз:* {prayer_name_ru}\n"
        status_text += f"   ⏰ Был в: `{times[previous_prayer[0]]}`\n"
        status_text += f"   ⌛ Прошло: `{hours_passed} ч {minutes_passed} мин`\n\n"
    else:
        status_text += "📌 Еще не было намазов сегодня\n\n"
    
    if next_prayer:
        prayer_name_ru = PRAYER_NAMES.get(next_prayer[0], next_prayer[0])
        time_left = next_prayer[1] - now
        
        if time_left.total_seconds() > 0:
            hours_left = time_left.seconds // 3600
            minutes_left = (time_left.seconds % 3600) // 60
            
            if next_prayer[0] == 'Fajr' and next_prayer[1].date() > now.date():
                next_day_str = next_prayer[1].strftime("%d.%m")
                next_day_times = prayer_data.get(next_day_str, {})
                next_time = next_day_times.get('Fajr', '--:--')
            else:
                next_time = times.get(next_prayer[0], '--:--')
            
            status_text += f"📌 *Следующий намаз:* {prayer_name_ru}\n"
            status_text += f"   ⏰ Будет в: `{next_time}`\n"
            status_text += f"   ⏱ Осталось: `{hours_left} ч {minutes_left} мин`\n"
        else:
            status_text += f"📌 *Следующий намаз:* {prayer_name_ru} уже должен быть!\n"
    else:
        status_text += "📌 Нет информации о следующем намазе\n"
    
    return status_text

# ==================== СИСТЕМА УВЕДОМЛЕНИЙ ====================
async def send_prayer_notification(prayer_name, prayer_time_str, prayer_data_today):
    """Отправляет уведомление о времени намаза с улучшенной обработкой ошибок"""
    print(f"🔔 Пытаюсь отправить уведомление для {prayer_name} в {prayer_time_str}")
    
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
            f"• Треть ночи: `{first_third}`\n"
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
    
    success_count = 0
    error_count = 0
    
    if not subscribed_users:
        print("⚠️ Нет подписанных пользователей для отправки уведомлений")
        return
    
    for user_id in subscribed_users:
        try:
            await bot.send_message(user_id, notification_text, parse_mode="Markdown")
            success_count += 1
            print(f"✅ Уведомление отправлено пользователю {user_id}")
        except Exception as e:
            error_count += 1
            print(f"❌ Ошибка отправки пользователю {user_id}: {e}")
            
            if "bot was blocked" in str(e).lower() or "user is deactivated" in str(e).lower():
                subscribed_users.discard(user_id)
                print(f"🗑️ Пользователь {user_id} удален из подписок")
    
    print(f"📊 Итог: отправлено {success_count}, ошибок {error_count}")
    
    if error_count > 0:
        save_subscriptions()

def schedule_prayer_notifications():
    """Планирует уведомления о намазах на сегодня с улучшенной обработкой ошибок"""
    print("\n⏰ Начинаю планирование уведомлений...")
    
    old_jobs = len(scheduler.get_jobs())
    scheduler.remove_all_jobs()
    print(f"🗑️ Удалено старых заданий: {old_jobs}")
    
    today = datetime.now(TIMEZONE)
    today_str = today.strftime("%d.%m")
    times = prayer_data.get(today_str, {})
    
    print(f"📅 Сегодня: {today_str}")
    print(f"🕐 Текущее время: {today.strftime('%H:%M:%S')}")
    
    if not times:
        print("❌ Нет данных о намазах на сегодня")
        return
    
    print("✅ Данные на сегодня найдены")
    
    prayers = [
        ("Фаджр", times['Fajr']),
        ("Зухр", times['Duhr']),
        ("Аср", times['Asr']),
        ("Магриб", times['Maghrib']),
        ("Иша", times['Isha'])
    ]
    
    scheduled_count = 0
    
    for prayer_name, prayer_time_str in prayers:
        try:
            prayer_hour, prayer_minute = map(int, prayer_time_str.split(':'))
            prayer_datetime = today.replace(
                hour=prayer_hour, 
                minute=prayer_minute, 
                second=0, 
                microsecond=0
            )
            
            if prayer_datetime < today:
                print(f"⏭️ Пропускаем {prayer_name} ({prayer_time_str}) - время уже прошло")
                continue
            
            job_id = f"{prayer_name}_{today_str}"
            
            scheduler.add_job(
                send_prayer_notification,
                CronTrigger(
                    hour=prayer_hour,
                    minute=prayer_minute,
                    timezone=TIMEZONE
                ),
                args=[prayer_name, prayer_time_str, times],
                id=job_id,
                misfire_grace_time=300,
                coalesce=True
            )
            
            scheduled_count += 1
            print(f"✅ Запланировано: {prayer_name} на {prayer_time_str} (ID: {job_id})")
            
        except ValueError as e:
            print(f"❌ Ошибка парсинга времени для {prayer_name} ({prayer_time_str}): {e}")
        except Exception as e:
            print(f"❌ Ошибка планирования {prayer_name}: {e}")
    
    print(f"📋 Итог планирования: запланировано {scheduled_count} из {len(prayers)} намазов")
    
    jobs = scheduler.get_jobs()
    if jobs:
        print("\n📅 Запланированные уведомления:")
        for job in jobs:
            next_run = job.next_run_time.astimezone(TIMEZONE) if job.next_run_time else "Не запланировано"
            print(f"   • {job.id}: {next_run}")
    else:
        print("⚠️ Нет запланированных уведомлений")

# ==================== КОМАНДЫ И ОБРАБОТЧИКИ БОТА ====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    
    subscribed_users.add(user_id)
    save_subscriptions()
    
    welcome_text = (
        "🕌 *Ассаламу алейкум!*\n\n"
        "Я бот с расписанием намазов для Черкесска.\n\n"
        "✅ *Вы автоматически подписаны на уведомления!*\n"
        "⏰ Уведомления приходят в точное время намазов\n\n"
        "*Используйте меню внизу: 👇*"
    )
    
    await message.answer(
        welcome_text, 
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )

@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    """Показывает статус уведомлений"""
    today = datetime.now(TIMEZONE)
    today_str = today.strftime("%d.%m")
    times = prayer_data.get(today_str, {})
    
    status_text = f"🔔 *Статус уведомлений*\n\n"
    status_text += f"📅 Сегодня: {today_str}\n"
    status_text += f"👥 Ваш ID: {message.from_user.id}\n"
    status_text += f"🔔 Ваша подписка: {'✅ ВКЛ' if message.from_user.id in subscribed_users else '❌ ВЫКЛ'}\n\n"
    
    if times:
        status_text += f"📋 *Расписание на сегодня:*\n"
        for prayer in ['Фаджр', 'Зухр', 'Аср', 'Магриб', 'Иша']:
            eng_name = {'Фаджр': 'Fajr', 'Зухр': 'Duhr', 'Аср': 'Asr', 'Магриб': 'Maghrib', 'Иша': 'Isha'}[prayer]
            if eng_name in times:
                status_text += f"• {prayer}: `{times[eng_name]}`\n"
    
    jobs = scheduler.get_jobs()
    if jobs:
        status_text += f"\n📅 *Запланировано уведомлений:* {len(jobs)}\n"
        for job in jobs[:3]:
            next_run = job.next_run_time.astimezone(TIMEZONE) if job.next_run_time else "—"
            prayer_name = job.id.split('_')[0]
            status_text += f"• {prayer_name}: {next_run.strftime('%H:%M') if next_run != '—' else '—'}\n"
    else:
        status_text += "\n⚠️ Нет запланированных уведомлений"
    
    await message.answer(status_text, parse_mode="Markdown")
    log_notification_status()

@dp.message(lambda message: message.text == "🕐 Сегодня")
async def handle_today_button(message: types.Message):
    """Обработчик кнопки Сегодня"""
    today = datetime.now(TIMEZONE)
    times = get_prayer_times(today)
    
    if times:
        response = format_prayer_times(times, today)
        await message.answer(
            response, 
            parse_mode=None,
            reply_markup=get_main_menu_keyboard()
        )
        
        status = get_current_prayer_status(times)
        await message.answer(
            status,
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await message.answer(
            "❌ Данные на сегодня не найдены",
            reply_markup=get_main_menu_keyboard()
        )

@dp.message(lambda message: message.text == "⏩ Завтра")
async def handle_tomorrow_button(message: types.Message):
    """Обработчик кнопки Завтра"""
    tomorrow = datetime.now(TIMEZONE) + timedelta(days=1)
    times = get_prayer_times(tomorrow)
    
    if times:
        response = format_prayer_times(times, tomorrow)
        await message.answer(
            response, 
            parse_mode=None,
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await message.answer(
            "❌ Данные на завтра не найдены",
            reply_markup=get_main_menu_keyboard()
        )

@dp.message(lambda message: message.text == "🗓️ Месяц")
async def handle_month_button(message: types.Message):
    """Обработчик кнопки Месяц"""
    await message.answer(
        "📅 *Выберите месяц:*",
        parse_mode="Markdown",
        reply_markup=get_months_keyboard()
    )

@dp.message(lambda message: message.text == "🔔 Вкл уведомления")
async def handle_notify_on_button(message: types.Message):
    """Обработчик кнопки Вкл уведомления"""
    user_id = message.from_user.id
    subscribed_users.add(user_id)
    save_subscriptions()
    await message.answer(
        "✅ Уведомления включены! Вы будете получать напоминания в точное время намазов.", 
        reply_markup=get_main_menu_keyboard()
    )

@dp.message(lambda message: message.text == "🔕 Выкл уведомления")
async def handle_notify_off_button(message: types.Message):
    """Обработчик кнопки Выкл уведомления"""
    user_id = message.from_user.id
    if user_id in subscribed_users:
        subscribed_users.remove(user_id)
        save_subscriptions()
    await message.answer(
        "🔕 Уведомления выключены.", 
        reply_markup=get_main_menu_keyboard()
    )

@dp.message(lambda message: message.text == "📊 Статус")
async def handle_status_button(message: types.Message):
    """Обработчик кнопки Статус"""
    await cmd_status(message)

@dp.message(lambda message: message.text == "ℹ️ Информация")
async def handle_info_button(message: types.Message):
    """Обработчик кнопки Информация"""
    info_text = (
        "🕌 *Расписание намазов для города Черкесска.*\n\n"
        "📍 *Местоположение:* \nЧеркесск (КЧР)\n"
        "🌐 *Координаты:* \n44.22333, 42.05778\n\n"
        "📝 *Хадис:*\n"
        "«Самое лучшее деяние — это намаз, совершенный в начале отведенного для него времени».\n"
        "Этот хадис передали ат-Тирмизи и аль-Хаким."
    )
    await message.answer(
        info_text, 
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )

@dp.message(lambda message: message.text == "🔄 Обновить")
async def handle_refresh_button(message: types.Message):
    """Обработчик кнопки Обновить"""
    await cmd_start(message)

@dp.callback_query()
async def handle_inline_buttons(callback: types.CallbackQuery):
    """Обработчик inline кнопок"""
    data = callback.data
    
    if data.startswith("month_"):
        try:
            month_num = int(data.split("_")[1])
            
            month_data = {}
            for day in range(1, 32):
                date_str = f"{day:02d}.{month_num:02d}"
                if date_str in prayer_data:
                    month_data[date_str] = prayer_data[date_str]
            
            if month_data:
                response = format_month_table(month_data, month_num)
                await callback.message.edit_text(
                    response, 
                    parse_mode=None
                )
            else:
                month_name_ru = MONTHS_RU.get(month_num, f"Месяц {month_num}")
                await callback.message.edit_text(
                    f"❌ Данные на {month_name_ru} не найдены",
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            await callback.message.edit_text(
                f"❌ Ошибка: {str(e)}",
                parse_mode="Markdown"
            )
    
    elif data == "back_to_menu":
        await callback.message.delete()
        await callback.message.answer(
            "👇 *Используйте меню внизу:*",
            parse_mode="Markdown",
            reply_markup=get_main_menu_keyboard()
        )
    
    await callback.answer()

# ==================== ЗАПУСК БОТА ====================
async def on_startup():
    """Действия при запуске бота"""
    print("=" * 50)
    print("🚀 Бот запускается...")
    print(f"✅ Токен получен: {API_TOKEN[:10]}...")
    print(f"🌐 Часовой пояс: {TIMEZONE}")
    print("=" * 50)
    
    if not load_prayer_data():
        print("❌ Критическая ошибка: не удалось загрузить данные CSV!")
        return
    
    load_subscriptions()
    print(f"👥 Загружено подписок: {len(subscribed_users)}")
    
    print("\n⏰ Планирую уведомления...")
    schedule_prayer_notifications()
    
    scheduler.start()
    print("✅ Планировщик уведомлений запущен")
    
    scheduler.add_job(
        schedule_prayer_notifications,
        CronTrigger(hour=0, minute=1, timezone=TIMEZONE),
        id="daily_schedule_update"
    )
    print("✅ Ежедневное обновление настроено на 00:01")
    
    log_notification_status()
    
    print("=" * 50)
    print("✅ Бот успешно запущен!")
    print("=" * 50)

async def main():
    """Основная функция запуска бота"""
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import os
import csv
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
import pytz

# ==================== ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ====================
try:
    load_dotenv()
except:
    print("⚠️ .env файл не найден, используем системные переменные")

# ==================== НАСТРОЙКИ ====================
API_TOKEN = os.getenv('API_TOKEN') or os.environ.get('API_TOKEN')

if not API_TOKEN:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: Не найден API_TOKEN!")
    print("✅ На bothost.ru добавьте переменную окружения: API_TOKEN=ваш_токен")
    exit(1)

CSV_FILE = 'prayer_times_cherkessk.csv'
SUBSCRIPTIONS_FILE = 'subscriptions.json'
TIMEZONE = pytz.timezone('Europe/Moscow')

# Русские названия месяцев
MONTHS_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
    5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
    9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
}

# Названия намазов на русском
PRAYER_NAMES = {
    'Fajr': 'Фаджр',
    'Sunrise': 'Восх',
    'Duhr': 'Зухр', 
    'Asr': 'Аср',
    'Maghrib': 'Магр',
    'Isha': 'Иша'
}

# Порядок намазов для вывода
PRAYER_ORDER = ['Fajr', 'Sunrise', 'Duhr', 'Asr', 'Maghrib', 'Isha']
# Порядок для детального вывода (день)
DETAILED_PRAYER_ORDER = ['Fajr', 'Sunrise', 'Duhr', 'Asr', 'Maghrib', 'Isha', 'FirstThird', 'Midnight', 'LastThird']

# Порядок намазов для временного расчета
TIME_PRAYER_ORDER = ['Fajr', 'Duhr', 'Asr', 'Maghrib', 'Isha']

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

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
def get_main_menu_keyboard():
    """Основное меню внизу экрана"""
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
                types.KeyboardButton(text="ℹ️ Информация"),
                types.KeyboardButton(text="🔄 Обновить")
            ]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )
    return keyboard

def get_months_keyboard():
    """Клавиатура с месяцами (inline)"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    # Добавляем кнопки по 3 в ряд
    months_row = []
    for month_num, month_name in MONTHS_RU.items():
        months_row.append(
            InlineKeyboardButton(text=month_name, callback_data=f"month_{month_num}")
        )
        if len(months_row) == 3:
            keyboard.inline_keyboard.append(months_row)
            months_row = []
    
    if months_row:  # Добавляем оставшиеся
        keyboard.inline_keyboard.append(months_row)
    
    # Кнопка возврата
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")
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
    """Форматирует время намазов для вывода (один день)"""
    if not times:
        return "📭 Данные для этой даты не найдены"
    
    if date_obj is None:
        date_obj = datetime.now(TIMEZONE)
    
    # Названия для детального вывода
    detailed_names = {
        'Fajr': '🌄 Фаджр:',
        'Sunrise': 'Восход:',
        'Duhr': '☀️ Зухр:',
        'Asr': '🌤 Аср:',
        'Maghrib': '🌅 Магриб:',
        'Isha': '🌙 Иша:',
        'FirstThird': 'Треть ночи:',
        'Midnight': 'Полночь:',
        'LastThird': 'Последняя треть:'
    }
    
    # Формируем строки с выравниванием
    lines = []
    
    # Заголовок
    month_name_ru = MONTHS_RU.get(date_obj.month, date_obj.strftime("%B"))
    lines.append(f"📅 {date_obj.day:02d} {month_name_ru}")
    lines.append(f"📍 Черкесск (КЧР)")
    lines.append("")
    
    # Находим максимальную длину названий для выравнивания
    max_name_length = max(len(detailed_names[prayer]) for prayer in DETAILED_PRAYER_ORDER if prayer in detailed_names)
    
    # Добавляем времена намазов с выравниванием
    for prayer in DETAILED_PRAYER_ORDER:
        if prayer in detailed_names and prayer in times:
            name = detailed_names[prayer]
            time_str = times[prayer]
            
            # Выравниваем названия до одинаковой длины
            aligned_name = name.ljust(max_name_length)
            lines.append(f"{aligned_name} {time_str}")
    
    return "\n".join(lines)

def format_month_table(times_dict, month_num):
    """Форматирует время намазов для вывода в виде таблицы на месяц"""
    if not times_dict:
        return "📭 Данные для этого месяца не найдены"
    
    month_name_ru = MONTHS_RU.get(month_num, f"Месяц {month_num}")
    
    # Заголовок с названиями намазов
    header = "Фаджр, Восх, Зухр, Аср, Магр, Иша"
    
    # Собираем строки для каждого дня
    day_lines = []
    
    for day in range(1, 32):
        date_str = f"{day:02d}.{month_num:02d}"
        if date_str in times_dict:
            times = times_dict[date_str]
            
            # Формируем строку времен для дня
            time_parts = []
            for prayer in PRAYER_ORDER:
                if prayer in times:
                    time_parts.append(times[prayer])
                else:
                    time_parts.append("--:--")
            
            time_str = ", ".join(time_parts)
            
            # Формируем строку дня
            day_line = f"{day:02d}. {month_name_ru}:\n{time_str}"
            day_lines.append(day_line)
    
    if not day_lines:
        return f"❌ Нет данных для {month_name_ru}"
    
    # Объединяем все
    result = header + "\n" + "\n".join(day_lines)
    return result

def get_current_prayer_status(times):
    """Возвращает информацию о текущем намазе: сколько прошло и сколько осталось"""
    now = datetime.now(TIMEZONE)
    current_time = now.time()
    
    # Создаем список времени намазов
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
    
    # Находим предыдущий и следующий намаз
    previous_prayer = None
    next_prayer = None
    
    for prayer, prayer_time in prayer_times:
        if prayer_time.time() <= current_time:
            previous_prayer = (prayer, prayer_time)
        elif prayer_time.time() > current_time and next_prayer is None:
            next_prayer = (prayer, prayer_time)
    
    # Если сейчас после последнего намаза (Иша)
    if previous_prayer and previous_prayer[0] == 'Isha':
        # Следующий намаз - Фаджр следующего дня
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
    
    # Формируем сообщение
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
            
            # Получаем время следующего намаза
            if next_prayer[0] == 'Fajr' and next_prayer[1].date() > now.date():
                # Фаджр следующего дня
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
    user_id = message.from_user.id
    
    # АВТОМАТИЧЕСКАЯ ПОДПИСКА
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

@dp.message(lambda message: message.text == "🕐 Сегодня")
async def handle_today_button(message: types.Message):
    """Обработка кнопки Сегодня"""
    today = datetime.now(TIMEZONE)
    times = get_prayer_times(today)
    
    if times:
        # Показываем расписание
        response = format_prayer_times(times, today)
        await message.answer(
            response, 
            parse_mode=None,  # Без форматирования Markdown
            reply_markup=get_main_menu_keyboard()
        )
        
        # Показываем статус
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
    """Обработка кнопки Завтра"""
    tomorrow = datetime.now(TIMEZONE) + timedelta(days=1)
    times = get_prayer_times(tomorrow)
    
    if times:
        response = format_prayer_times(times, tomorrow)
        await message.answer(
            response, 
            parse_mode=None,  # Без форматирования Markdown
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await message.answer(
            "❌ Данные на завтра не найдены",
            reply_markup=get_main_menu_keyboard()
        )

@dp.message(lambda message: message.text == "🗓️ Месяц")
async def handle_month_button(message: types.Message):
    """Обработка кнопки Месяц - показываем inline кнопки с месяцами"""
    await message.answer(
        "📅 *Выберите месяц:*",
        parse_mode="Markdown",
        reply_markup=get_months_keyboard()
    )

@dp.message(lambda message: message.text == "🔔 Вкл уведомления")
async def handle_notify_on_button(message: types.Message):
    """Обработка кнопки Вкл уведомления"""
    user_id = message.from_user.id
    subscribed_users.add(user_id)
    save_subscriptions()
    await message.answer(
        "✅ Уведомления включены! Вы будете получать напоминания в точное время намазов.", 
        reply_markup=get_main_menu_keyboard()
    )

@dp.message(lambda message: message.text == "🔕 Выкл уведомления")
async def handle_notify_off_button(message: types.Message):
    """Обработка кнопки Выкл уведомления"""
    user_id = message.from_user.id
    if user_id in subscribed_users:
        subscribed_users.remove(user_id)
        save_subscriptions()
    await message.answer(
        "🔕 Уведомления выключены.", 
        reply_markup=get_main_menu_keyboard()
    )

@dp.message(lambda message: message.text == "ℹ️ Информация")
async def handle_info_button(message: types.Message):
    """Обработка кнопки Информация"""
    info_text = (
        "🕌 *Информация о боте*\n\n"
        "🕌 *Расписание намазов для города Черкесска*\n"
        "📍 *Местоположение:* Черкесск (КЧР)\n"
        "🌐 *Координаты:* 44.22333, 42.05778\n\n"
        "📝 Передают со слов Ибн Мас‘уда, что Посланник, мир ему и благословение Аллаха, сказал:\n «Самое лучшее деяние — это намаз, совершенный в начале отведенного для него времени».\n Этот хадис передали ат-Тирмизи и аль-Хаким."
    )
    await message.answer(
        info_text, 
        parse_mode="Markdown",
        reply_markup=get_main_menu_keyboard()
    )

@dp.message(lambda message: message.text == "🔄 Обновить")
async def handle_refresh_button(message: types.Message):
    """Обработка кнопки Обновить"""
    await cmd_start(message)

# ==================== ОБРАБОТКА INLINE КНОПОК МЕСЯЦЕВ ====================
@dp.callback_query()
async def handle_inline_buttons(callback: types.CallbackQuery):
    """Обработка inline кнопок с месяцами"""
    data = callback.data
    
    if data.startswith("month_"):
        # Пользователь выбрал месяц
        try:
            month_num = int(data.split("_")[1])
            
            # Собираем данные за месяц
            month_data = {}
            for day in range(1, 32):
                date_str = f"{day:02d}.{month_num:02d}"
                if date_str in prayer_data:
                    month_data[date_str] = prayer_data[date_str]
            
            if month_data:
                response = format_month_table(month_data, month_num)
                await callback.message.edit_text(
                    response, 
                    parse_mode=None  # Без форматирования Markdown
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
        # Возвращаемся к меню
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
    print("🚀 Бот запускается...")
    print(f"✅ Токен получен: {API_TOKEN[:10]}...")
    
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
    
    print("✅ Бот успешно запущен!")

async def main():
    """Основная функция"""
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

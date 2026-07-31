import os
import time
import threading
import random
import string
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

TOKEN = '8898711498:AAEjsOmvU0HdWLqJNWTnreFCjsdXhr0hX9w'
bot = telebot.TeleBot(TOKEN)

WEB_APP_URL = "https://tg-wheel-iota.vercel.app/" 
DIKIDI_URL = "https://dikidi.ru/1883903"

ADMIN_ID = 1868467281 

LOG_FILE = "wheel_results.txt"
USERS_FILE = "used_users.txt"

# --- ПРАВКА: Абсолютный путь к картинке ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TAKSA_IMAGE = os.path.join(BASE_DIR, "taksa.jpg")

# Словарь для отслеживания статуса подтверждения: promo_code -> True/False
active_timers = {}

# Словарь для привязки промокода к ID пользователя: promo_code -> user_id
promo_to_user = {}

# --- РАБОТА С ПАМЯТЬЮ И ПРОМОКОДАМИ ---

def load_used_users():
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return set(int(line.strip()) for line in f if line.strip().isdigit())

def save_used_user(user_id):
    with open(USERS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{user_id}\n")

def generate_promo_code():
    letters_and_digits = string.ascii_uppercase + string.digits
    code = ''.join(random.choice(letters_and_digits) for _ in range(4))
    return f"SIREN-{code}"

used_users = load_used_users()

def log_result(user, prize, promo_code, status="АКТИВЕН"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    username = f"@{user.username}" if user.username else "Без юзернейма"
    first_name = user.first_name or "Без имени"
    
    log_line = f"[{now}] ID: {user.id} | Name: {first_name} | Username: {username} | Promo: {promo_code} | Статус: {status} | Приз: {prize}\n"
    
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_line)


# --- ФОНОВАЯ ЛОГИКА ТАЙМЕРОВ (15 СЕК + 10 СЕК) ---

def start_timer_chain(user_chat_id, promo_code, prize):
    """Фоновая функция контроля таймера админа"""
    
    # 1. Ждем 15 секунд
    time.sleep(15)
    
    # Проверяем, подтвердил ли админ
    if active_timers.get(promo_code) == True:
        return # Если подтвердил — останавливаем цепочку

    # 2. Шлем сообщение про 10 секунд
    try:
        bot.send_message(
            user_chat_id,
            "⚠️ Если ты не гомосек, запишись за 10 сек!"
        )
    except Exception as e:
        print(f"Ошибка отправки предупреждения: {e}")

    # 3. Ждем еще 10 секунд
    time.sleep(10)

    # Повторная проверка
    if active_timers.get(promo_code) == True:
        return # Успел подтвердить в последний момент!

    # 4. Время вышло — сгорание!
    active_timers[promo_code] = "EXPIRED"
    
    print(f"🔍 Ищем файл по пути: {TAKSA_IMAGE}")
    
    try:
        # Отправляем фото таксы, если файл существует
        if os.path.exists(TAKSA_IMAGE):
            with open(TAKSA_IMAGE, "rb") as photo:
                bot.send_photo(
                    user_chat_id, 
                    photo, 
                    caption="хахаха вот ты лох, не успел 😂"
                )
            print("✅ Картинка успешно отправлена!")
        else:
            print(f"⚠️ Файл НЕ НАЙДЕН по пути: {TAKSA_IMAGE}")
            bot.send_message(
                user_chat_id, 
                "хахаха вот ты лох, не успел 😂"
            )
            
        # Уведомляем админа, что время вышло
        bot.send_message(
            ADMIN_ID,
            f"⏳ Время вышло! Промокод {promo_code} пользователя сгорел по таймеру."
        )
    except Exception as e:
        print(f"Ошибка сгорания: {e}")


# --- ПОДТВЕРЖДЕНИЕ ЧЕРЕЗ ОТВЕТ НА СООБЩЕНИЕ КОМАНДОЙ /yes ---

# --- ПОДТВЕРЖДЕНИЕ ЧЕРЕЗ ОТВЕТ НА СООБЩЕНИЕ КОМАНДОЙ /yes ---

@bot.message_handler(commands=['yes'])
def confirm_by_reply(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ У вас нет прав!")
        return

    if not message.reply_to_message:
        bot.send_message(
            message.chat.id, 
            "⚠️ Эту команду нужно отправлять **в ответ** на сообщение о выигрыше от бота!", 
            parse_mode="Markdown"
        )
        return

    reply_text = message.reply_to_message.text or ""
    
    import re
    # Ищем промокод
    match_promo = re.search(r"SIREN-[A-Z0-9]{4}", reply_text)
    
    # Универсальный поиск UserID (найдет и с апострофами, и без них)
    match_user = re.search(r"UserID:\s*`?(\d+)`?", reply_text)
    
    if not match_promo:
        bot.send_message(message.chat.id, "❌ В тексте сообщения не найден промокод!")
        return
        
    promo_code = match_promo.group(0)
    
    # Достаем user_id из текста или из запасного словаря
    user_id = int(match_user.group(1)) if match_user else promo_to_user.get(promo_code)

    if not user_id:
        bot.send_message(message.chat.id, "❌ Не удалось определить ID пользователя для этого промокода.")
        return

    # Проверяем, не использован ли уже
    if active_timers.get(promo_code) == True:
        bot.send_message(message.chat.id, f"⚠️ Промокод {promo_code} уже был использован ранее!")
        return

    # Проверяем таймер сгорания
    if active_timers.get(promo_code) == "EXPIRED":
        bot.send_message(message.chat.id, f"⏳ Промокод {promo_code} уже сгорел по таймеру!")
        return

    # Подтверждаем
    active_timers[promo_code] = True

    # Отправляем уведомление клиенту
    try:
        bot.send_message(
            user_id,
            "🎉 Промокод успешно применен! Ждем вас в гости по вашему выигрышу! ❤️"
        )
    except Exception as e:
        print(f"Ошибка отправки сообщения клиенту: {e}")
        bot.send_message(message.chat.id, f"⚠️ Ошибка отправки сообщения клиенту: {e}")
        return

    # Уведомляем администратора
    bot.send_message(
        message.chat.id, 
        f"✅ Промокод {promo_code} успешно подтвержден! Клиенту отправлено уведомление."
    )

# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['stats'])
def send_stats(message):
    if message.from_user.id == ADMIN_ID:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "rb") as f:
                bot.send_document(message.chat.id, f, caption="📊 Актуальная статистика выигрышей")
        else:
            bot.send_message(message.chat.id, "📁 Файл статистики пока пуст.")
    else:
        bot.send_message(message.chat.id, "⛔ У вас нет прав для выполнения этой команды.")

@bot.message_handler(commands=['clear'])
def clear_used_users(message):
    if message.from_user.id == ADMIN_ID:
        global used_users
        used_users.clear()
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            f.write("")
        bot.send_message(message.chat.id, "🧹 Список пользователей очищен! Теперь все могут крутить колесо снова.")
    else:
        bot.send_message(message.chat.id, "⛔ У вас нет прав для выполнения этой команды.")

        
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    
    if user_id in used_users and user_id != ADMIN_ID:
        bot.send_message(
            message.chat.id, 
            "⛔ Вы уже использовали попытку! Повторный запуск недоступен.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    web_app_button = KeyboardButton(
        text="🚀 Открыть приложение", 
        web_app=WebAppInfo(url=WEB_APP_URL)
    )
    markup.add(web_app_button)
    
    bot.send_message(
        message.chat.id, 
        "Нажми на кнопку внизу экрана, чтобы крутить колесо:", 
        reply_markup=markup
    )


@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    user = message.from_user
    prize = message.web_app_data.data 
    promo_code = generate_promo_code()
    
    # 1. Сохраняем пользователя
    used_users.add(user.id)
    save_used_user(user.id)
    log_result(user, prize, promo_code)
    
    # Инициализируем статус таймера
    active_timers[promo_code] = False
    
    # 2. Сообщение пользователю с ссылкой на Dikidi
    dikidi_keyboard = InlineKeyboardMarkup()
    dikidi_button = InlineKeyboardButton(text="📅 Записаться в Dikidi", url=DIKIDI_URL)
    dikidi_keyboard.add(dikidi_button)
    
    user_text = (
        f"📩 Результат сохранен!\n\n"
        f"Твой приз: {prize} 🎉\n"
        f"Твой промокод: {promo_code}\n\n"
        f"⏰ Вы можете воспользоваться выигрышем в течение 14 дней.\n"
        f"Запишитесь к нам по ссылке ниже или через администратора @dashka_dulyar👇"
    )
    
    bot.send_message(
        message.chat.id, 
        user_text,
        reply_markup=ReplyKeyboardRemove()
    )
    
    bot.send_message(
        message.chat.id,
        "Жми для записи:",
        reply_markup=dikidi_keyboard
    )
    
# 3. Уведомление АДМИНУ с кнопкой подтверждения (БЕЗ parse_mode, чтобы не было ошибок разметки)
    admin_keyboard = InlineKeyboardMarkup()
    confirm_button = InlineKeyboardButton(
        text="✅ Подтвердить запись", 
        callback_data=f"confirm_{promo_code}_{user.id}"
    )
    admin_keyboard.add(confirm_button)
    
    username_str = f"@{user.username}" if user.username else "без юзернейма"
    first_name = user.first_name or "Пользователь"
    
    bot.send_message(
        ADMIN_ID,
        f"🔔 Новый выигрыш в рулетке!\n\n"
        f"👤 Пользователь: {first_name} ({username_str})\n"
        f"🎁 Приз: {prize}\n"
        f"🔑 Промокод: {promo_code}\n"
        f"🆔 UserID: {user.id}\n\n"
        f"⏱ У вас есть 25 секунд, чтобы подтвердить запись!",
        reply_markup=admin_keyboard
    )
    
    # 4. Запускаем фоновый поток таймеров (обязательно возвращаем на место!)
    timer_thread = threading.Thread(
        target=start_timer_chain, 
        args=(message.chat.id, promo_code, prize)
    )
    timer_thread.start()

print("Бот запущен! Ждет сообщений...")
bot.polling(none_stop=True)
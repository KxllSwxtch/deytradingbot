import json
import telebot
import os
import re
import requests
import locale
import logging
import urllib.parse
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from database import (
    create_tables,
    get_orders,
    get_all_orders,
    add_order,
    update_user_phone,
    update_order_status_in_db,
    delete_order_from_db,
    update_user_name,
    update_user_name,
    get_calculation_count,
    increment_calculation_count,
    check_user_subscription,
    update_user_subscription,
    get_all_users,
    add_or_update_user,
    user_exists,
    get_all_bot_users,
)
from bs4 import BeautifulSoup
from io import BytesIO
from telebot import types
from dotenv import load_dotenv
from types import SimpleNamespace
from urllib.parse import urlparse, parse_qs
from utils import (
    generate_encar_photo_url,
    clean_number,
    get_customs_fees,
    calculate_age,
    format_number,
    get_customs_fees_manual,
    get_panauto_car_data,
)

CALCULATE_CAR_TEXT = "Рассчитать Автомобиль (Encar, KBChaCha, ChutCha)"
CHANNEL_USERNAME = "dey_trading"
BOT_TOKEN = os.getenv("BOT_TOKEN")

load_dotenv()
bot_token = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(bot_token)

# Set locale for number formatting
locale.setlocale(locale.LC_ALL, "en_US.UTF-8")

# Storage for the last error message ID
last_error_message_id = {}

# global variables
car_data = {}
car_id_external = ""
total_car_price = 0
krw_rub_rate = 0
rub_to_krw_rate = 0
usd_rate = 0
users = set()
user_data = {}

car_month = None
car_year = None

vehicle_id = None
vehicle_no = None

usd_to_krw_rate = 0
usd_to_rub_rate = 0

usdt_to_krw_rate = 0


################## КОД ДЛЯ СТАТУСОВ
# Храним заказы пользователей
pending_orders = {}
user_contacts = {}
user_names = {}

# Хранение контекста для ввода мощности двигателя (HP)
pending_hp_input = {}

# Маппинг типов топлива для calcus.ru API
# 1 = Бензиновый (Petrol)
# 2 = Дизельный (Diesel)
# 4 = Электрический (Electric)
# 5 = Последовательный гибрид (Series Hybrid)
# 6 = Параллельный гибрид (Parallel Hybrid)
FUEL_TYPE_MAPPING = {
    # Korean fuel names from Encar/KBChaCha APIs
    "가솔린": 1,      # Gasoline
    "휘발유": 1,      # Gasoline (alt)
    "디젤": 2,        # Diesel
    "경유": 2,        # Diesel (alt)
    "LPG": 1,         # Treat as gasoline
    "전기": 4,        # Electric
    "하이브리드": 6,  # Hybrid (parallel)
    "플러그인하이브리드": 6,  # Plug-in hybrid
    # Russian translations (from pan-auto API fuelType field)
    "Бензин": 1,
    "Дизель": 2,
    "Электро": 4,
    "Гибрид": 6,
}
DEFAULT_FUEL_TYPE = 1  # Gasoline as default

MANAGERS = [728438182, 627689711]

FREE_ACCESS_USERS = {728438182, 627689711}

ORDER_STATUSES = {
    "1": "🚗 Авто выкуплен (на базе)",
    "2": "🚢 Отправлен в порт г. Пусан на погрузку",
    "3": "🌊 В пути во Владивосток",
    "4": "🛃 Таможенная очистка",
    "5": "📦 Погрузка до МСК",
    "6": "🚛 Доставляется клиенту",
}


@bot.callback_query_handler(func=lambda call: call.data.startswith("add_favorite_"))
def add_favorite_car(call):
    global car_data
    user_id = call.message.chat.id

    if not car_data or "name" not in car_data:
        bot.answer_callback_query(
            call.id, "🚫 Ошибка: Данные о машине отсутствуют.", show_alert=True
        )
        return

    # Проверяем, есть ли авто уже в избранном
    existing_orders = get_orders(user_id)
    if any(order["id"] == car_data.get("car_id") for order in existing_orders):
        bot.answer_callback_query(call.id, "✅ Этот автомобиль уже в избранном.")
        return

    # Получаем данные пользователя
    user = bot.get_chat(user_id)
    user_name = user.username if user.username else "Неизвестно"

    # Проверяем, есть ли сохранённый номер телефона пользователя
    phone_number = user_contacts.get(user_id, "Неизвестно")

    # Формируем объект заказа
    order_data = {
        "user_id": user_id,
        "car_id": car_data.get("car_id", "Нет ID"),
        "title": car_data.get("name", "Неизвестно"),
        "price": f"₩{format_number(car_data.get('car_price', 0))}",
        "link": car_data.get("link", "Нет ссылки"),
        "year": car_data.get("year", "Неизвестно"),
        "month": car_data.get("month", "Неизвестно"),
        "mileage": car_data.get("mileage", "Неизвестно"),
        "fuel": car_data.get("fuel", "Неизвестно"),
        "engine_volume": car_data.get("engine_volume", "Неизвестно"),
        "transmission": car_data.get("transmission", "Неизвестно"),
        "images": car_data.get("images", []),
        "status": "🔄 Не заказано",
        "total_cost_usd": car_data.get("total_cost_usd", 0),
        "total_cost_krw": car_data.get("total_cost_krw", 0),
        "total_cost_rub": car_data.get("total_cost_rub", 0),
        "user_name": user_name,  # ✅ Добавляем user_name
        "phone_number": phone_number,  # ✅ Добавляем phone_number (если нет, "Неизвестно")
    }

    # Логируем, чтобы проверить, какие данные отправляем в БД
    print(f"✅ Добавляем заказ: {order_data}")

    # Сохраняем в базу
    add_order(order_data)

    # Подтверждаем пользователю
    bot.answer_callback_query(
        call.id, "⭐ Автомобиль добавлен в избранное!", show_alert=True
    )


@bot.message_handler(commands=["my_cars"])
def show_favorite_cars(message):
    user_id = message.chat.id
    orders = get_orders(user_id)  # Берём заказы из БД

    if not orders:
        bot.send_message(user_id, "❌ У вас нет сохранённых автомобилей.")
        return

    for car in orders:
        car_id = car["car_id"]  # Используем car_id вместо id
        car_title = car["title"]
        car_status = car["status"]
        car_link = car["link"]
        car_year = car["year"]
        car_month = car["month"]
        car_mileage = car["mileage"]
        car_engine_volume = car["engine_volume"]
        car_transmission = car["transmission"]
        total_cost_usd = car["total_cost_usd"]
        total_cost_krw = car["total_cost_krw"]
        total_cost_rub = car["total_cost_rub"]

        # Формируем текст сообщения
        response_text = (
            f"🚗 *{car_title} ({car_id})*\n\n"
            f"📅 {car_month}/{car_year} | ⚙️ {car_transmission}\n"
            f"🔢 Пробег: {car_mileage} | 🏎 Объём: {format_number(car_engine_volume)} cc\n\n"
            f"Стоимость авто под ключ:\n"
            f"${format_number(total_cost_usd)} | ₩{format_number(total_cost_krw)} | {format_number(total_cost_rub)} ₽\n\n"
            f"📌 *Статус:* {car_status}\n\n"
            f"[🔗 Ссылка на автомобиль]({car_link})\n\n"
            f"Консультация с менеджером:\n\n"
            f"+82-10-8855-03865 (Андрей)\n"
        )

        # Создаём клавиатуру
        keyboard = types.InlineKeyboardMarkup()
        if car_status == "🔄 Не заказано":
            keyboard.add(
                types.InlineKeyboardButton(
                    f"📦 Заказать {car_title}",
                    callback_data=f"order_car_{car_id}",
                )
            )
        keyboard.add(
            types.InlineKeyboardButton(
                "Вернуться в главное меню", callback_data="main_menu"
            )
        )

        bot.send_message(
            user_id, response_text, parse_mode="Markdown", reply_markup=keyboard
        )


@bot.callback_query_handler(func=lambda call: call.data == "show_orders")
def callback_show_orders(call):
    """Обработчик кнопки 'Посмотреть список заказов'"""
    manager_id = call.message.chat.id
    print(f"📋 Менеджер {manager_id} нажал 'Посмотреть список заказов'")

    # ✅ Вызываем show_orders() с переданным сообщением из callback-запроса
    show_orders(call.message)


def notify_managers(order):
    """Отправляем информацию о заказе всем менеджерам"""
    print(f"📦 Отправляем заказ менеджерам: {order}")

    # Создаём клавиатуру с кнопкой "Посмотреть список заказов"
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "📋 Посмотреть список заказов", callback_data="show_orders"
        )
    )

    order_title = order.get("title", "Без названия")
    order_link = order.get("link", "#")
    user_name = order.get("user_name", "Неизвестный")
    user_id = order.get("user_id", None)
    phone_number = order.get("phone_number", "Не указан")

    user_mention = f"[{user_name}](tg://user?id={user_id})" if user_id else user_name

    message_text = (
        f"🚨 *Новый заказ!*\n\n"
        f"🚗 [{order_title}]({order_link})\n"
        f"👤 Заказчик: {user_mention}\n"
        f"📞 Контакт: {phone_number}\n"
        f"📌 *Статус:* 🕒 Ожидает подтверждения\n"
    )

    for manager_id in MANAGERS:
        bot.send_message(
            manager_id,
            message_text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("order_car_"))
def order_car(call):
    user_id = call.message.chat.id
    car_id = call.data.split("_")[-1]

    # Получаем авто из базы
    user_orders = get_orders(user_id)
    order_found = None

    for order in user_orders:
        if str(order["car_id"]) == str(car_id):
            order_found = order
            break
        else:
            print(f"❌ Автомобиль {car_id} не совпадает с {order['car_id']}")

    if not order_found:
        print(f"❌ Ошибка: авто {car_id} не найдено в базе!")
        bot.send_message(user_id, "❌ Ошибка: автомобиль не найден.")
        return

    # ✅ Проверяем, есть ли ФИО у пользователя
    if user_id not in user_names:
        print(f"📝 Запрашиваем ФИО у {user_id}")
        bot.send_message(
            user_id,
            "📝 Введите ваше *ФИО* для оформления заказа:",
            parse_mode="Markdown",
        )

        # Сохраняем ID заказа в `pending_orders`
        pending_orders[user_id] = car_id
        return

    # ✅ Если ФИО уже есть, проверяем телефон
    if user_id not in user_contacts:
        print(f"📞 Запрашиваем телефон у {user_id}")
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        button = types.KeyboardButton("📞 Отправить номер", request_contact=True)
        markup.add(button)

        bot.send_message(
            user_id,
            "📲 Для оформления заказа, пожалуйста, отправьте номер телефона, "
            "на который зарегистрирован WhatsApp или Telegram.",
            reply_markup=markup,
        )

        # Сохраняем ID заказа в `pending_orders`
        pending_orders[user_id] = car_id
        return

    # ✅ Если ФИО и телефон уже есть → обновляем заказ
    phone_number = user_contacts[user_id]
    full_name = user_names[user_id]

    update_order_status(car_id, "🕒 Ожидает подтверждения")
    update_order_status_in_db(order_found["id"], "🕒 Ожидает подтверждения")

    bot.send_message(
        user_id,
        f"✅ Ваш заказ на {order_found['title']} оформлен!\n"
        f"📌 Статус: 🕒 Ожидает подтверждения\n"
        f"📞 Контакт для связи: {phone_number}\n"
        f"👤 ФИО: {full_name}",
        callback_data="show_orders",
    )

    # ✅ Добавляем ФИО в заказ перед отправкой менеджерам
    order_found["user_name"] = full_name
    notify_managers(order_found)


# Обработчик получения номера телефона
@bot.message_handler(content_types=["contact"])
def handle_contact(message):
    if not message.contact or not message.contact.phone_number:
        bot.send_message(user_id, "❌ Ошибка: номер телефона не передан.")
        return

    user_id = message.chat.id
    phone_number = message.contact.phone_number

    # Сохраняем номер телефона
    user_contacts[user_id] = phone_number
    bot.send_message(user_id, f"✅ Ваш номер {phone_number} сохранён!")

    # Проверяем, есть ли ожидаемый заказ
    if user_id not in pending_orders:
        bot.send_message(user_id, "✅ Ваш номер сохранён, но активного заказа нет.")
        return

    if user_id in pending_orders:
        car_id = pending_orders[user_id]  # Берём car_id из `pending_orders`
        print(f"📦 Пользователь {user_id} подтвердил заказ автомобиля {car_id}")

        # Получаем заказанное авто из базы
        user_orders = get_orders(user_id)
        order_found = None

        for order in user_orders:
            if str(order["car_id"]).strip() == str(car_id).strip():
                order_found = order
                break

        if not order_found:
            bot.send_message(user_id, "❌ Ошибка: автомобиль не найден в базе данных.")
            return

        # Добавляем `user_id` в order_found, если его нет
        order_found["user_id"] = user_id
        order_found["phone_number"] = (
            phone_number  # ✅ Сохраняем номер телефона в заказе
        )

        print(
            f"🛠 Обновляем телефон {phone_number} для user_id={user_id}, order_id={order_found['id']}"
        )
        update_user_phone(user_id, phone_number, order_found["id"])
        update_order_status_in_db(order_found["id"], "🕒 Ожидает подтверждения")

        bot.send_message(
            user_id,
            f"✅ Ваш заказ на {order_found['title']} оформлен!\n"
            f"📌 Статус: 🕒 Ожидает подтверждения\n"
            f"📞 Контакт: {phone_number}",
        )

        notify_managers(order_found)


@bot.message_handler(
    func=lambda message: not message.text.startswith("/")
    and message.chat.id in pending_orders
)
def handle_full_name(message):
    user_id = message.chat.id
    full_name = message.text.strip()

    # ❌ Если ФИО пустое, просим ввести заново
    if not full_name:
        bot.send_message(
            user_id, "❌ ФИО не может быть пустым. Введите ваше ФИО ещё раз:"
        )
        return

    # ✅ Сохраняем ФИО
    user_names[user_id] = full_name
    bot.send_message(user_id, f"✅ Ваше ФИО '{full_name}' сохранено!")

    # Проверяем, есть ли ожидаемый заказ
    car_id = pending_orders[user_id]  # Берём car_id из `pending_orders`
    print(
        f"📦 Пользователь {user_id} подтвердил заказ автомобиля {car_id} с ФИО {full_name}"
    )

    # Получаем заказанное авто из базы
    user_orders = get_orders(user_id)
    order_found = next(
        (
            order
            for order in user_orders
            if str(order["car_id"]).strip() == str(car_id).strip()
        ),
        None,
    )

    if not order_found:
        bot.send_message(user_id, "❌ Ошибка: автомобиль не найден в базе данных.")
        return

    # ✅ Обновляем статус заказа и добавляем ФИО в БД
    import hashlib

    def convert_car_id(car_id):
        if car_id.isdigit():
            return int(car_id)  # Если уже число, просто вернуть его
        else:
            return int(hashlib.md5(car_id.encode()).hexdigest(), 16) % (
                10**9
            )  # Преобразуем в число

    # Пример использования
    numeric_car_id = convert_car_id(car_id)

    update_order_status_in_db(order_found["id"], "🕒 Ожидает подтверждения")
    update_user_name(user_id, full_name)

    # ✅ Проверяем, есть ли уже телефон пользователя
    if user_id not in user_contacts:
        print(f"📞 Запрашиваем телефон у {user_id}")
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        button = types.KeyboardButton("📞 Отправить номер", request_contact=True)
        markup.add(button)

        bot.send_message(
            user_id,
            "📲 Теперь отправьте ваш *номер телефона*, на который зарегистрирован WhatsApp или Telegram.",
            reply_markup=markup,
            parse_mode="Markdown",
        )
        return  # Ждём телефон, дальше не идём

    # ✅ Если телефон уже есть → завершаем оформление
    phone_number = user_contacts[user_id]

    bot.send_message(
        user_id,
        f"✅ Ваш заказ на {order_found['title']} оформлен!\n"
        f"📌 Статус: 🕒 Ожидает подтверждения\n"
        f"📞 Контакт: {phone_number}\n"
        f"👤 ФИО: {full_name}",
    )

    # ✅ Отправляем информацию менеджерам
    order_found["user_name"] = full_name
    print(f"📦 Перед отправкой менеджерам заказ: {order_found}")  # Отладка
    notify_managers(order_found)

    # ✅ Удаляем `pending_orders`
    del pending_orders[user_id]


# Функция оформления заказа
def process_order(user_id, car_id, username, phone_number):
    # Достаём авто из списка
    car = next(
        (car for car in user_orders.get(user_id, []) if car["id"] == car_id), None
    )

    if not car:
        bot.send_message(user_id, "❌ Ошибка: автомобиль не найден.")
        return

    car_title = car.get("title", "Неизвестно")
    car_link = car.get("link", "Нет ссылки")

    # Менеджер, которому отправлять заявку
    manager_chat_id = MANAGERS[0]  # Здесь нужно указать ID менеджера

    # Сообщение менеджеру
    manager_text = (
        f"📢 *Новый заказ на автомобиль!*\n\n"
        f"🚗 {car_title}\n"
        f"🔗 [Ссылка на автомобиль]({car_link})\n\n"
        f"🔹 Username: @{username if username else 'Не указан'}\n"
        f"📞 Телефон: {phone_number if phone_number else 'Не указан'}\n"
    )

    bot.send_message(manager_chat_id, manager_text, parse_mode="Markdown")

    # Обновляем статус авто
    car["status"] = "🕒 Ожидает подтверждения"
    bot.send_message(
        user_id,
        f"✅ Ваш заказ на {car_title} оформлен! Менеджер скоро свяжется с вами.",
    )


@bot.message_handler(commands=["orders"])
def show_orders(message):
    manager_id = message.chat.id

    # Проверяем, является ли пользователь менеджером
    if manager_id not in MANAGERS:
        bot.send_message(manager_id, "❌ У вас нет доступа к заказам.")
        return

    # Загружаем все заказы из базы данных
    orders = get_all_orders()

    if not orders:
        bot.send_message(manager_id, "📭 Нет активных заказов.")
        return

    for idx, order in enumerate(orders, start=1):
        order_id = order.get("id", "Неизвестно")
        car_title = order.get("title", "Без названия")
        user_id = order.get("user_id")
        user_name = order.get("user_name", "Неизвестный")
        phone_number = order.get("phone_number", "Неизвестно")
        car_status = order.get("status", "🕒 Ожидает подтверждения")
        car_link = order.get("link", "#")
        car_id = order.get("car_id", "Неизвестно")

        if car_status == "🔄 Не заказано":
            car_status = "🕒 Ожидает подтверждения"

        user_mention = (
            f"[{user_name}](tg://user?id={user_id})" if user_id else user_name
        )

        response_text = (
            # f"📦 *Заказ #{idx}*\n"
            f"🚗 *{car_title}* (ID: {car_id})\n\n"
            f"👤 Заказчик: {user_mention}\n"
            f"📞 Телефон: *{phone_number}*\n\n"
            f"📌 *Статус:* {car_status}\n\n"
            f"[🔗 Ссылка на автомобиль]({car_link})"
        )

        # Создаем клавиатуру
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                f"📌 Обновить статус ({car_title})",
                callback_data=f"update_status_{order_id}",
            ),
            types.InlineKeyboardButton(
                f"🗑 Удалить заказ ({car_title})",
                callback_data=f"delete_order_{order_id}",
            ),
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Вернуться в главное меню ", callback_data="main_menu"
            )
        )

        bot.send_message(
            manager_id,
            response_text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


@bot.message_handler(commands=["stats"])
def show_stats(message):
    admin_id = message.chat.id

    # Проверяем, является ли пользователь администратором
    if admin_id not in MANAGERS:
        bot.send_message(admin_id, "❌ У вас нет доступа к статистике.")
        return

    # Получаем список всех пользователей
    users = get_all_bot_users()

    if not users:
        bot.send_message(admin_id, "📊 Статистика: пользователей не найдено.")
        return

    stats_message = "📊 Статистика пользователей:\n\n"

    for idx, user in enumerate(users, start=1):
        user_id = user.get("user_id")
        username = user.get("username", "")
        first_name = user.get("first_name", "")
        last_name = user.get("last_name", "")

        # Формируем имя пользователя
        if first_name and last_name:
            user_name = f"{first_name} {last_name}"
        elif first_name:
            user_name = first_name
        elif username:
            user_name = username
        else:
            user_name = f"User {user_id}"

        # Форматируем username
        username_display = f"(@{username})" if username else ""

        # Форматируем дату первой активности
        first_activity = user.get("created_at")
        if first_activity:
            try:
                # Если first_activity - строка, преобразуем в datetime
                if isinstance(first_activity, str):
                    first_activity = datetime.strptime(
                        first_activity, "%Y-%m-%d %H:%M:%S"
                    )
                # Форматируем дату
                activity_date = first_activity.strftime("%Y-%m-%d")
            except (ValueError, AttributeError):
                # Если возникла ошибка при форматировании, используем как есть
                if isinstance(first_activity, str):
                    parts = first_activity.split(" ")
                    activity_date = parts[0] if parts else "Неизвестно"
                else:
                    activity_date = str(first_activity)
        else:
            activity_date = "Неизвестно"

        # Добавляем информацию о пользователе в сообщение
        user_info = f"👤 {idx}. {user_name} {username_display}"
        if username_display == "":
            user_info = f"👤 {idx}. {user_name}"

        stats_message += f"{user_info} — {activity_date}\n"

        # Если сообщение становится слишком длинным, отправляем его и начинаем новое
        if len(stats_message) > 3500:
            bot.send_message(admin_id, stats_message)
            stats_message = ""

    # Отправляем оставшуюся часть сообщения
    if stats_message:
        bot.send_message(admin_id, stats_message)

    # Отправляем общую статистику
    total_stats = (
        f"📈 *Общая статистика*\n\n"
        f"👥 Всего пользователей: {len(users)}\n"
        f"🔢 Всего расчётов: {sum(user.get('calc_count', 0) or 0 for user in users)}\n"
        f"📝 С подпиской: {sum(1 for user in users if user.get('subscription'))}"
    )

    bot.send_message(admin_id, total_stats, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith("update_status_"))
def update_order_status(call):
    manager_id = call.message.chat.id
    order_id = call.data.split("_")[-1]  # ❗ Здесь приходит ID заказа, а не car_id

    print(f"🔍 Менеджер {manager_id} пытается обновить статус заказа {order_id}")

    # Получаем заказы из базы
    orders = get_all_orders()  # ✅ Загружаем все заказы
    # print(f"📦 Все заказы из базы: {orders}")  # Логируем заказы

    # 🛠 Теперь ищем по `id`, а не по `car_id`
    order_found = next(
        (order for order in orders if str(order["id"]) == str(order_id)), None
    )

    if not order_found:
        print(f"❌ Ошибка: заказ {order_id} не найден!")
        bot.answer_callback_query(call.id, "❌ Ошибка: заказ не найден.")
        return

    user_id = order_found["user_id"]
    car_id = order_found["car_id"]  # ✅ Берём car_id

    # 🔥 Генерируем кнопки статусов
    keyboard = types.InlineKeyboardMarkup()
    for status_code, status_text in ORDER_STATUSES.items():
        keyboard.add(
            types.InlineKeyboardButton(
                status_text,
                callback_data=f"set_status_{user_id}_{order_id}_{status_code}",
            )
        )

    bot.send_message(manager_id, "📌 Выберите новый статус:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_order_"))
def delete_order(call):
    manager_id = call.message.chat.id
    order_id = call.data.split("_")[-1]

    print(f"🗑 Менеджер {manager_id} хочет удалить заказ {order_id}")

    # Удаляем заказ из базы
    delete_order_from_db(order_id)

    bot.answer_callback_query(call.id, "✅ Заказ удалён!")
    bot.send_message(manager_id, f"🗑 Заказ {order_id} успешно удалён.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("set_status_"))
def set_new_status(call):
    manager_id = call.message.chat.id

    print(f"🔄 Получен `callback_data`: {call.data}")  # Логирование данных

    # Разбиваем callback_data
    _, _, user_id, order_id, status_code = call.data.split("_", 4)

    if not user_id.isdigit():
        print(f"❌ Ошибка: user_id некорректный: {user_id}")
        bot.answer_callback_query(call.id, "❌ Ошибка: неверный ID пользователя.")
        return

    user_id = int(user_id)

    # Проверяем статус
    if status_code not in ORDER_STATUSES:
        print(f"❌ Ошибка: неверный код статуса: {status_code}")
        bot.answer_callback_query(call.id, "❌ Ошибка: неверный статус.")
        return

    new_status = ORDER_STATUSES[status_code]  # Получаем текст статуса по коду

    print(
        f"🔄 Менеджер {manager_id} меняет статус заказа {order_id} для {user_id} на {new_status}"
    )

    # Получаем все заказы
    orders = get_all_orders()
    # print(f"📦 Все заказы пользователя {user_id}: {orders}")  # Логируем

    # 🛠 Ищем заказ по `id`
    order_found = next(
        (order for order in orders if str(order["id"]) == str(order_id)), None
    )

    if not order_found:
        print(f"❌ Ошибка: заказ {order_id} не найден!")
        bot.answer_callback_query(call.id, "❌ Ошибка: заказ не найден.")
        return

    # Обновляем статус заказа в БД
    update_order_status_in_db(order_id, new_status)

    # Уведомляем клиента
    bot.send_message(
        user_id,
        f"📢 *Обновление статуса заказа!*\n\n"
        f"🚗 [{order_found['title']}]({order_found['link']})\n"
        f"📌 Новый статус:\n*{new_status}*",
        parse_mode="Markdown",
    )

    # Подтверждаем менеджеру
    bot.answer_callback_query(call.id, f"✅ Статус обновлён на {new_status}!")

    # Обновляем заказы у менеджеров
    show_orders(call.message)


@bot.callback_query_handler(func=lambda call: call.data.startswith("place_order_"))
def place_order(call):
    user_id = call.message.chat.id
    order_id = call.data.split("_")[-1]

    # Проверяем, есть ли этот заказ
    if order_id not in user_orders:
        bot.answer_callback_query(call.id, "❌ Ошибка: заказ не найден.")
        return

    order = user_orders[order_id]

    # Создаём кнопку "Обновить статус" (только для менеджеров)
    keyboard = types.InlineKeyboardMarkup()
    if user_id in MANAGERS:
        keyboard.add(
            types.InlineKeyboardButton(
                "📌 Обновить статус", callback_data=f"update_status_{order_id}"
            )
        )

    bot.send_message(
        user_id,
        f"📢 *Заказ оформлен!*\n\n"
        f"🚗 [{order['title']}]({order['link']})\n"
        f"👤 Клиент: [{order['user_name']}](tg://user?id={order['user_id']})\n"
        f"📌 *Текущий статус:* {order['status']}",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )

    bot.answer_callback_query(call.id, "✅ Заказ отправлен менеджерам!")


# def archive_completed_orders():
#     global user_orders
#     completed_orders = []

#     # Проверяем все заказы всех пользователей
#     for user_id, orders in user_orders.items():
#         for order in orders:
#             if (
#                 order["status"] == "🚛 Доставляется клиенту"
#             ):  # ✅ Проверяем как элемент списка
#                 completed_orders.append(order)

#         # Убираем завершённые заказы из активных
#         user_orders[user_id] = [
#             order for order in orders if order["status"] != "🚛 Доставляется клиенту"
#         ]

#     print(f"📦 Архивировано {len(completed_orders)} заказов")  # Логирование


################## КОД ДЛЯ СТАТУСОВ


@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def check_subscription(call):
    user_id = call.from_user.id
    chat_member = bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)

    if chat_member.status in ["member", "administrator", "creator"]:
        bot.answer_callback_query(
            call.id, "✅ Подписка оформлена! Вы можете продолжить расчёты."
        )
        # Установить подписку для пользователя в БД
        update_user_subscription(user_id, True)
    else:
        bot.answer_callback_query(
            call.id,
            "🚫 Вы не подписались на канал! Оформите подписку, чтобы продолжить.",
        )


def is_user_subscribed(user_id):
    """Проверяет, подписан ли пользователь на канал."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember?chat_id={CHANNEL_USERNAME}&user_id={user_id}"

    try:
        http_response = requests.get(url, timeout=5)
        http_response.raise_for_status()
        response = http_response.json()

        return response.get("ok") and response.get("result", {}).get("status") in [
            "member",
            "administrator",
            "creator",
        ]
    except requests.exceptions.Timeout:
        logging.error(f"Timeout checking subscription for user {user_id}")
        return False
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error checking subscription: {e}")
        return False
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error checking subscription: {e}")
        return False
    except Exception as e:
        logging.error(f"Unexpected error in is_user_subscribed: {e}")
        return False


def print_message(message):
    print("\n\n##############")
    print(f"{message}")
    print("##############\n\n")
    return None


# Функция для установки команд меню
def set_bot_commands():
    commands = [
        types.BotCommand("start", "Запустить бота"),
        types.BotCommand("exchange_rates", "Курсы валют"),
        types.BotCommand("my_cars", "Мои избранные автомобили"),
        types.BotCommand("orders", "Список заказов (Для менеджеров)"),
    ]

    # Проверяем, является ли пользователь менеджером
    user_id = bot.get_me().id
    if user_id in MANAGERS:
        commands.extend(
            [
                types.BotCommand("orders", "Просмотр всех заказов (для менеджеров)"),
                types.BotCommand("stats", "Статистика пользователей"),
            ]
        )

    bot.set_my_commands(commands)


def get_usdt_to_krw_rate():
    global usdt_to_krw_rate

    # URL для получения курса USDT к KRW
    url = "https://api.coinbase.com/v2/exchange-rates?currency=USDT"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Извлечение курса KRW
        krw_rate = data["data"]["rates"]["KRW"]
        usdt_to_krw_rate = float(krw_rate)

        print(f"Курс USDT к KRW -> {str(usdt_to_krw_rate)}")

        return float(krw_rate) + 8

    except requests.exceptions.Timeout:
        logging.error("Timeout while fetching USDT to KRW rate from Coinbase")
        # Return default rate if API fails
        return 1350.0  # Approximate fallback rate
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error fetching USDT rate: {e}")
        return 1350.0
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error for Coinbase API: {e}")
        return 1350.0
    except (KeyError, ValueError, TypeError) as e:
        logging.error(f"Error parsing USDT rate data: {e}")
        return 1350.0
    except Exception as e:
        logging.error(f"Unexpected error in get_usdt_to_krw_rate: {e}")
        return 1350.0


def get_rub_to_krw_rate():
    global rub_to_krw_rate

    url = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/rub.json"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Проверяем, что запрос успешный (код 200)
        data = response.json()

        rub_to_krw = data["rub"]["krw"]  # Достаем курс рубля к воне
        rub_to_krw_rate = rub_to_krw

        print(f"Курс RUB → KRW: {rub_to_krw_rate}")

    except requests.exceptions.Timeout:
        logging.error("Timeout while fetching RUB to KRW rate")
        rub_to_krw_rate = 14.0  # Fallback rate
    except requests.RequestException as e:
        logging.error(f"Ошибка при получении курса RUB → KRW: {e}")
        rub_to_krw_rate = 14.0
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error for RUB to KRW rate: {e}")
        rub_to_krw_rate = 14.0
    except (KeyError, TypeError, ValueError) as e:
        logging.error(f"Error parsing RUB to KRW rate data: {e}")
        rub_to_krw_rate = 14.0
    except Exception as e:
        logging.error(f"Unexpected error in get_rub_to_krw_rate: {e}")
        rub_to_krw_rate = 14.0


def get_currency_rates():
    global usd_rate, usd_to_krw_rate, usd_to_rub_rate

    print_message("ПОЛУЧАЕМ КУРСЫ ВАЛЮТ")

    # Получаем курс USD → KRW
    get_usd_to_krw_rate()

    # Получаем курс USD → RUB
    get_usd_to_rub_rate()

    rates_text = (
        f"USD → KRW: <b>{usd_to_krw_rate:.2f} ₩</b>\n"
        f"USD → RUB: <b>{usd_to_rub_rate:.2f} ₽</b>"
    )

    return rates_text


# Функция для получения курсов валют с API
def get_usd_to_krw_rate():
    global usd_to_krw_rate

    url = "https://api.manana.kr/exchange/rate/KRW/USD.json"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Проверяем успешность запроса
        data = response.json()

        # Получаем курс и добавляем +25 KRW
        usd_to_krw = data[0]["rate"] + 10
        usd_to_krw_rate = usd_to_krw

        print(f"Курс USD → KRW (с учетом +25 KRW): {usd_to_krw_rate}")
    except requests.exceptions.Timeout:
        logging.error("Timeout while fetching USD to KRW rate")
        usd_to_krw_rate = 1340.0  # Fallback rate
    except requests.RequestException as e:
        logging.error(f"Ошибка при получении курса USD → KRW: {e}")
        usd_to_krw_rate = 1340.0
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error for USD to KRW rate: {e}")
        usd_to_krw_rate = 1340.0
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logging.error(f"Error parsing USD to KRW rate data: {e}")
        usd_to_krw_rate = 1340.0
    except Exception as e:
        logging.error(f"Unexpected error in get_usd_to_krw_rate: {e}")
        usd_to_krw_rate = 1340.0


def get_usd_to_rub_rate():
    global usd_to_rub_rate

    url = "https://mosca.moscow/api/v1/rate/"
    headers = {
        "Access-Token": "JI_piVMlX9TsvIRKmduIbZOWzLo-v2zXozNfuxxXj4_MpsUKd_7aQS16fExzA7MVFCVVoAAmrb_-aMuu_UIbJA"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Проверяем успешность запроса
        data = response.json()

        # Получаем курс USD → RUB
        usd_to_rub = data["buy"]
        usd_to_rub_rate = usd_to_rub

        print(f"Курс USD → RUB: {usd_to_rub_rate}")
    except requests.exceptions.Timeout:
        logging.error("Timeout while fetching USD to RUB rate")
        usd_to_rub_rate = 95.0  # Fallback rate
    except requests.RequestException as e:
        logging.error(f"Ошибка при получении курса USD → RUB: {e}")
        usd_to_rub_rate = 95.0
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error for USD to RUB rate: {e}")
        usd_to_rub_rate = 95.0
    except (KeyError, TypeError, ValueError) as e:
        logging.error(f"Error parsing USD to RUB rate data: {e}")
        usd_to_rub_rate = 95.0
    except Exception as e:
        logging.error(f"Unexpected error in get_usd_to_rub_rate: {e}")
        usd_to_rub_rate = 95.0


# Обработчик команды /cbr
@bot.message_handler(commands=["exchange_rates"])
def cbr_command(message):
    try:
        rates_text = get_currency_rates()

        # Создаем клавиатуру с кнопкой для расчета автомобиля
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "Рассчитать стоимость автомобиля", callback_data="calculate_another"
            )
        )

        # Отправляем сообщение с курсами и клавиатурой
        bot.send_message(
            message.chat.id, rates_text, reply_markup=keyboard, parse_mode="HTML"
        )
    except Exception as e:
        bot.send_message(
            message.chat.id, "Не удалось получить курсы валют. Попробуйте позже."
        )
        print(f"Ошибка при получении курсов валют: {e}")


# Main menu creation function
def main_menu():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    keyboard.add(
        types.KeyboardButton(CALCULATE_CAR_TEXT),
        types.KeyboardButton("Ручной расчёт"),
        # types.KeyboardButton("Заказ запчастей"),
    )
    keyboard.add(
        types.KeyboardButton("Написать менеджеру"),
        types.KeyboardButton("О нас"),
        types.KeyboardButton("Telegram-канал"),
        # types.KeyboardButton("Написать в WhatsApp"),
        types.KeyboardButton("Instagram"),
        types.KeyboardButton("ВКонтакте"),
        # types.KeyboardButton("Facebook"),
    )
    return keyboard


# Start command handler
@bot.message_handler(commands=["start"])
def send_welcome(message):
    get_currency_rates()

    user_first_name = message.from_user.first_name

    # Добавляем пользователя в базу данных
    user_data = {
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "last_name": message.from_user.last_name,
        "phone_number": user_contacts.get(message.from_user.id, None),
    }
    add_or_update_user(user_data)

    welcome_message = (
        f"Здравствуйте, {user_first_name}!\n\n"
        "Я бот компании DeyTrading. Я помогу вам рассчитать стоимость понравившегося вам автомобиля из Южной Кореи до стран СНГ.\n\n"
        "Выберите действие из меню ниже."
    )

    # Логотип компании
    logo_path = "assets/logo.png"

    with open(logo_path, "rb") as logo_file:
        bot.send_photo(
        message.chat.id,
        photo=types.InputFile(logo_file),
    )

    # Отправляем приветственное сообщение
    bot.send_message(message.chat.id, welcome_message, reply_markup=main_menu())


# Error handling function
def send_error_message(message, error_text):
    global last_error_message_id

    # Remove previous error message if it exists
    if last_error_message_id.get(message.chat.id):
        try:
            bot.delete_message(message.chat.id, last_error_message_id[message.chat.id])
        except Exception as e:
            logging.error(f"Error deleting message: {e}")

    # Send new error message and store its ID
    error_message = bot.reply_to(message, error_text, reply_markup=main_menu())
    last_error_message_id[message.chat.id] = error_message.id
    logging.error(f"Error sent to user {message.chat.id}: {error_text}")


def get_car_info(url):
    global car_id_external, vehicle_no, vehicle_id, car_year, car_month

    if "fem.encar.com" in url:
        car_id_match = re.findall(r"\d+", url)
        car_id = car_id_match[0]
        car_id_external = car_id

        url = f"https://api.encar.com/v1/readside/vehicle/{car_id}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": "http://www.encar.com/",
            "Accept": "application/json",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
        }

        try:
            # Make HTTP request with timeout
            http_response = requests.get(url, headers=headers, timeout=10)

            # Log response status and content for debugging
            logging.info(f"Encar API Response Status: {http_response.status_code}")

            # Check if request was successful
            if http_response.status_code != 200:
                logging.error(f"Encar API returned status code {http_response.status_code}")
                logging.error(f"Response content: {http_response.text[:500]}")
                return None

            # Try to parse JSON
            response = http_response.json()

        except requests.exceptions.Timeout:
            logging.error(f"Timeout while requesting Encar API for car_id: {car_id}")
            return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Request error while fetching Encar data: {e}")
            return None
        except json.JSONDecodeError as e:
            logging.error(f"JSON decode error for Encar API. Response was: {http_response.text[:500]}")
            logging.error(f"Error details: {e}")
            return None
        except Exception as e:
            logging.error(f"Unexpected error in get_car_info (Encar): {e}")
            return None

        # Validate response structure
        try:
            # Информация об автомобиле
            car_make = response["category"]["manufacturerEnglishName"]  # Марка
            car_model = response["category"]["modelGroupEnglishName"]  # Модель
            car_trim = response["category"]["gradeDetailEnglishName"] or ""  # Комплектация
        except (KeyError, TypeError) as e:
            logging.error(f"Invalid response structure from Encar API: {e}")
            logging.error(f"Response keys: {response.keys() if isinstance(response, dict) else 'Not a dict'}")
            return None

        try:
            car_title = f"{car_make} {car_model} {car_trim}"  # Заголовок

            # Получаем все необходимые данные по автомобилю
            car_price = str(response["advertisement"]["price"])
            car_date = response["category"]["yearMonth"]
            year = car_date[2:4]
            month = car_date[4:]
            car_year = year
            car_month = month

            # Пробег (форматирование)
            mileage = response["spec"]["mileage"]
            formatted_mileage = f"{mileage:,} км"

            # Тип КПП
            transmission = response["spec"]["transmissionName"]
            formatted_transmission = "Автомат" if "오토" in transmission else "Механика"

            car_engine_displacement = str(response["spec"]["displacement"])
            car_type = response["spec"]["bodyName"]

            # Список фотографий (берем первые 10)
            car_photos = [
                generate_encar_photo_url(photo["path"]) for photo in response["photos"][:10]
            ]
            car_photos = [url for url in car_photos if url]

            # Дополнительные данные
            vehicle_no = response["vehicleNo"]
            vehicle_id = response["vehicleId"]

            # Форматируем
            formatted_car_date = f"01{month}{year}"
            formatted_car_type = "crossover" if car_type == "SUV" else "sedan"

            print_message(
                f"ID: {car_id}\nType: {formatted_car_type}\nDate: {formatted_car_date}\nCar Engine Displacement: {car_engine_displacement}\nPrice: {car_price} KRW"
            )

            return [
                car_price,
                car_engine_displacement,
                formatted_car_date,
                car_title,
                formatted_mileage,
                formatted_transmission,
                car_photos,
                year,
                month,
            ]
        except (KeyError, TypeError, IndexError) as e:
            logging.error(f"Error extracting car data from Encar response: {e}")
            return None
    elif "kbchachacha.com" in url:
        url = f"https://www.kbchachacha.com/public/car/detail.kbc?carSeq={car_id_external}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "Connection": "keep-alive",
        }

        response = requests.get(url=url, headers=headers)
        soup = BeautifulSoup(response.text, "html.parser")

        # Находим JSON в <script type="application/ld+json">
        json_script = soup.find("script", {"type": "application/ld+json"})
        if json_script:
            json_data = json.loads(json_script.text.strip())

            # Извлекаем данные
            car_name = json_data.get("name", "Неизвестная модель")
            car_images = json_data.get("image", [])[:10]  # Берем первые 10 фото
            car_price = json_data.get("offers", {}).get("price", "Не указано")

            # Находим таблицу с информацией
            table = soup.find("table", {"class": "detail-info-table"})
            if table:
                rows = table.find_all("tr")

                # Достаём данные
                car_number = None
                car_year = None
                car_mileage = None
                car_fuel = None
                car_engine_displacement = None

                for row in rows:
                    headers = row.find_all("th")
                    values = row.find_all("td")

                    for th, td in zip(headers, values):
                        header_text = th.text.strip()
                        value_text = td.text.strip()

                        if header_text == "차량정보":  # Номер машины
                            car_number = value_text
                        elif header_text == "연식":  # Год выпуска
                            car_year = value_text
                        elif header_text == "주행거리":  # Пробег
                            car_mileage = value_text
                        elif header_text == "연료":  # Топливо
                            car_fuel = value_text
                        elif header_text == "배기량":  # Объем двигателя
                            car_engine_displacement = value_text
            else:
                print("❌ Таблица информации не найдена")

            # Если объем двигателя не найден или равен 0, пытаемся извлечь из названия
            if not car_engine_displacement or car_engine_displacement == "0cc":
                # Ищем числа с точкой (например, 2.0) в названии автомобиля
                engine_match = re.search(r"(\d+\.\d+)", car_name)
                if engine_match:
                    # Преобразуем, например, 2.0 в 2000cc
                    engine_size = float(engine_match.group(1))
                    car_engine_displacement = f"{int(engine_size * 1000)}cc"
                    print(
                        f"✅ Извлечен объем двигателя из названия: {car_engine_displacement}"
                    )
                else:
                    # Ищем просто числа (например, 2000) в названии
                    engine_match = re.search(r"(\d{3,4})", car_name)
                    if engine_match and 500 <= int(engine_match.group(1)) <= 9000:
                        car_engine_displacement = f"{engine_match.group(1)}cc"
                        print(
                            f"✅ Извлечен объем двигателя из названия: {car_engine_displacement}"
                        )

            car_info = {
                "name": car_name,
                "car_price": car_price,
                "images": car_images,
                "number": car_number,
                "year": car_year,
                "mileage": car_mileage,
                "fuel": car_fuel,
                "engine_volume": car_engine_displacement,
                "transmission": "오토",
            }

            return car_info
        else:
            print(
                "❌ Не удалось найти JSON-данные в <script type='application/ld+json'>"
            )
    elif "chutcha" in url:
        print("🔍 Парсим Chutcha.net...")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en,ru;q=0.9,en-CA;q=0.8,la;q=0.7,fr;q=0.6,ko;q=0.5",
            "Referer": "https://web.chutcha.net/bmc/search?brandGroup=1&modelTree=%7B%7D&priceRange=0%2C0&mileage=0%2C0&year=&saleType=&accident=&fuel=&transmission=&region=&color=&option=&cpo=&theme=&sort=1&currPage=&carType=",
        }

        response = requests.get(url, headers=headers)

        soup = BeautifulSoup(response.text, "lxml")

        # Extract JSON data from <script type="application/ld+json">
        script_tag = soup.find("script", {"type": "application/json"})
        vehicle_data = None

        if not script_tag:
            return "Error: JSON data not found"

        try:
            data = json.loads(script_tag.string)
        except json.JSONDecodeError:
            return "Error: Failed to parse JSON"

        # Перемещение к ldJson (содержит основную информацию о машине)
        vehicle_data = (
            data.get("props", {})
            .get("pageProps", {})
            .get("dehydratedState", {})
            .get("queries", [])[0]
            .get("state", {})
            .get("data", {})
        )

        # Получение изображений
        img_list_data = vehicle_data.get("img_list", [])
        img_list = []
        for query in img_list_data:
            img_list.append(
                f"https://imgsc.chutcha.kr{query.get('img_path','').replace('.jpg', '_ori.jpg')}?s=1024x768&t=crop"
            )

        name = (
            vehicle_data.get("base_info", {}).get("brand_name", "")
            + " "
            + vehicle_data.get("base_info", {}).get("model_name", "")
            + " "
            + vehicle_data.get("base_info", {}).get("sub_model_name", "")
            + " "
            + vehicle_data.get("base_info", {}).get("grade_name", "")
        )
        car_price = vehicle_data.get("base_info", {}).get("plain_price", "")
        car_number = vehicle_data.get("base_info", {}).get("number_plate", "")
        car_year = vehicle_data.get("base_info", {}).get("first_reg_year", "")[2:]
        car_month = str(
            vehicle_data.get("base_info", {}).get("first_reg_month", "")
        ).zfill(2)
        car_mileage = vehicle_data.get("base_info", {}).get("plain_mileage", "")
        car_fuel = vehicle_data.get("base_info", {}).get("fuel_name", "")
        car_engine_displacement = vehicle_data.get("base_info", {}).get(
            "displacement", ""
        )
        car_transmission = vehicle_data.get("base_info", {}).get(
            "transmission_name", ""
        )

        # Список всех страховых
        car_history = (
            vehicle_data.get("safe_info", {})
            .get("carhistory_safe", {})
            .get("insurance", {})
            .get("list", [])
        )

        # Инициализация сумм страховых выплат
        own_damage_total = 0  # Выплаты по текущему авто
        other_damage_total = 0  # Выплаты по другим авто

        # Обработка выплат, если они есть
        if car_history or len(car_history.get("price", "")) > 0:
            for claim in car_history:
                claim_type = claim.get("type")
                claim_price = (
                    int(claim["price"])
                    if claim.get("price") and claim["price"].isdigit()
                    else 0
                )

                if claim_type == "1":  # Выплаты по текущему авто
                    own_damage_total += claim_price
                elif claim_type == "2":  # Выплаты по другим авто
                    other_damage_total += claim_price

        # Формирование итогового JSON
        car_info = {
            "name": name,
            "car_price": car_price,
            "images": img_list,
            "number": car_number,
            "year": car_year,
            "month": car_month,
            "mileage": car_mileage,
            "fuel": car_fuel,
            "engine_volume": car_engine_displacement,
            "transmission": car_transmission,
            "insurance_claims": {
                "own_damage_total": own_damage_total if car_history else "Недоступно",
                "other_damage_total": (
                    other_damage_total if car_history else "Недоступно"
                ),
            },
        }

        return car_info


# Function to calculate the total cost
def calculate_cost(link, message):
    global car_data, car_id_external, car_month, car_year, krw_rub_rate, eur_rub_rate, rub_to_krw_rate, usd_rate, usdt_to_krw_rate

    user_id = message.chat.id

    # Добавляем пользователя в базу данных
    user_data = {
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "last_name": message.from_user.last_name,
        "phone_number": user_contacts.get(message.from_user.id, None),
    }
    add_or_update_user(user_data)

    # Если пользователь в списке FREE_ACCESS_USERS, он получает бесконечные расчёты
    if user_id in FREE_ACCESS_USERS:
        user_subscription = True
    else:
        # Проверяем подписку в БД
        user_subscription = check_user_subscription(user_id)

        # Если в БД нет подписки – проверяем через API
        if not user_subscription:
            user_subscription = is_user_subscribed(user_id)
            if user_subscription:
                update_user_subscription(user_id, True)  # ✅ Обновляем подписку в БД

    # Проверяем количество расчётов
    user_calc_count = get_calculation_count(user_id)

    if user_calc_count >= 2 and not user_subscription:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "🚀 Оформить подписку", url=f"https://t.me/{CHANNEL_USERNAME}"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton("✅ Готово", callback_data="check_subscription")
        )

        bot.send_message(
            message.chat.id,
            "🚫 У вас закончились бесплатные расчёты. Чтобы продолжить, оформите подписку.",
            reply_markup=keyboard,
        )
        return

    # Увеличиваем счётчик расчётов
    increment_calculation_count(user_id)

    print_message("ЗАПРОС НА РАСЧЁТ АВТОМОБИЛЯ")

    # Отправляем сообщение и сохраняем его ID
    processing_message = bot.send_message(
        message.chat.id, "Обрабатываю данные. Пожалуйста подождите ⏳"
    )

    car_id = None
    car_title = ""

    # Initialize pan-auto related variables (only used for Encar)
    panauto_data = None
    panauto_hp = None
    panauto_fuel_type = DEFAULT_FUEL_TYPE
    use_panauto_customs = False

    if "fem.encar.com" in link:
        car_id_match = re.findall(r"\d+", link)
        if car_id_match:
            car_id = car_id_match[0]  # Use the first match of digits
            car_id_external = car_id
            link = f"https://fem.encar.com/cars/detail/{car_id}"
        else:
            send_error_message(message, "🚫 Не удалось извлечь carid из ссылки.")
            return

    elif "kbchachacha.com" in link or "m.kbchachacha.com" in link:
        parsed_url = urlparse(link)
        query_params = parse_qs(parsed_url.query)

        # Попытка 1: обычный carSeq в параметрах
        car_id = query_params.get("carSeq", [None])[0]

        # Попытка 2: если есть параметр `c=...`, надо выполнить редирект
        if not car_id and query_params.get("c"):
            try:
                response = requests.get(link, allow_redirects=True, timeout=5)
                redirected_url = response.url
                redirected_query = parse_qs(urlparse(redirected_url).query)
                car_id = redirected_query.get("carSeq", [None])[0]
            except Exception as e:
                print(f"Ошибка при обработке редиректа KBChaCha: {e}")
                send_error_message(message, "🚫 Ошибка при обработке ссылки KBChaCha.")
                return

        if car_id:
            car_id_external = car_id
            link = f"https://www.kbchachacha.com/public/car/detail.kbc?carSeq={car_id}"
        else:
            send_error_message(message, "🚫 Не удалось извлечь carSeq из ссылки.")
            return

    elif "web.chutcha.net" in link:
        parsed_url = urlparse(link)
        path_parts = parsed_url.path.split("/")

        if len(path_parts) >= 4 and path_parts[-2] == "detail":
            car_id = path_parts[-1]  # Берём последний элемент из пути
            car_id_external = car_id
            link = f"https://web.chutcha.net/bmc/detail/{car_id}"
        else:
            send_error_message(
                message, "🚫 Не удалось извлечь ID автомобиля из ссылки Chutcha.net."
            )
            return

    else:
        # Извлекаем carid с URL encar
        parsed_url = urlparse(link)
        query_params = parse_qs(parsed_url.query)
        car_id = query_params.get("carid", [None])[0]

    # Если ссылка с encar
    if "fem.encar.com" in link:
        # First, try to get data from pan-auto API
        panauto_data = get_panauto_car_data(car_id)

        result = get_car_info(link)

        # Check if API request failed
        if result is None:
            bot.delete_message(message.chat.id, processing_message.message_id)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "Попробовать ещё раз",
                    callback_data="calculate_another",
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "Связаться с менеджером", url="https://t.me/DeyTrading6"
                )
            )
            bot.send_message(
                message.chat.id,
                "❌ Не удалось загрузить данные автомобиля с Encar.\n\n"
                "Возможные причины:\n"
                "• Автомобиль уже продан\n"
                "• Временные проблемы с API\n"
                "• Неверная ссылка\n\n"
                "Пожалуйста, попробуйте другой автомобиль или свяжитесь с менеджером.",
                reply_markup=keyboard,
            )
            return

        (
            car_price,
            car_engine_displacement,
            formatted_car_date,
            car_title,
            formatted_mileage,
            formatted_transmission,
            car_photos,
            year,
            month,
        ) = result

        preview_link = f"https://fem.encar.com/cars/detail/{car_id}"

        # Check if pan-auto has HP data
        panauto_hp = None
        panauto_fuel_type = DEFAULT_FUEL_TYPE
        use_panauto_customs = False

        if panauto_data:
            panauto_hp = panauto_data.get("hp")
            panauto_fuel_type_str = panauto_data.get("fuelType")
            if panauto_fuel_type_str:
                panauto_fuel_type = FUEL_TYPE_MAPPING.get(panauto_fuel_type_str, DEFAULT_FUEL_TYPE)

            # Check if HP is valid and customs data is available
            if panauto_hp and panauto_hp > 0:
                costs_rub = panauto_data.get("costs", {}).get("RUB", {})
                if costs_rub.get("clearanceCost") and costs_rub.get("customsDuty") and costs_rub.get("utilizationFee"):
                    use_panauto_customs = True

        # If HP is not available or invalid, ask user for HP
        if not panauto_hp or panauto_hp <= 0:
            bot.delete_message(message.chat.id, processing_message.message_id)

            # Save context for HP input
            car_engine_displacement_int = int(car_engine_displacement)
            price_krw = int(car_price) * 10000
            formatted_car_year = f"20{year}"

            pending_hp_input[user_id] = {
                "car_engine_displacement": car_engine_displacement_int,
                "price_krw": price_krw,
                "formatted_car_year": formatted_car_year,
                "car_month": month,
                "engine_type": panauto_fuel_type,
                "car_title": car_title,
                "formatted_mileage": formatted_mileage,
                "formatted_transmission": formatted_transmission,
                "car_photos": car_photos,
                "year": year,
                "month": month,
                "preview_link": preview_link,
                "link": link,
                "car_id": car_id,
            }

            msg = bot.send_message(
                message.chat.id,
                f"🚗 {car_title}\n\n"
                "Для расчёта таможенных платежей введите мощность двигателя (л.с.):\n"
                "(Эту информацию можно найти в техническом паспорте автомобиля)",
            )
            bot.register_next_step_handler(msg, process_hp_input)
            return

    # Если ссылка с kbchacha
    if "kbchachacha.com" in link:
        result = get_car_info(link)

        # Check if parsing failed
        if result is None:
            bot.delete_message(message.chat.id, processing_message.message_id)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "Попробовать ещё раз",
                    callback_data="calculate_another",
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "Связаться с менеджером", url="https://t.me/DeyTrading6"
                )
            )
            bot.send_message(
                message.chat.id,
                "❌ Не удалось загрузить данные автомобиля с KBChaCha.\n\n"
                "Пожалуйста, попробуйте другой автомобиль или свяжитесь с менеджером.",
                reply_markup=keyboard,
            )
            return

        car_title = result["name"]

        match = re.search(r"(\d{2})년(\d{2})월", result["year"])
        if match:
            car_year = match.group(1)
            car_month = match.group(2)  # Получаем двухзначный месяц
        else:
            car_year = "Не найдено"
            car_month = "Не найдено"

        month = car_month
        year = car_year

        car_engine_displacement = re.sub(r"[^\d]", "", result["engine_volume"])
        car_price = int(result["car_price"]) / 10000
        formatted_car_date = f"01{car_month}{match.group(1)}"
        formatted_mileage = result["mileage"]
        formatted_transmission = (
            "Автомат" if "오토" in result["transmission"] else "Механика"
        )
        car_photos = result["images"]

        preview_link = (
            f"https://www.kbchachacha.com/public/car/detail.kbc?carSeq={car_id}"
        )

        # Get fuel type from KBChaCha data
        car_fuel = result.get("fuel", "")
        kbchacha_fuel_type = FUEL_TYPE_MAPPING.get(car_fuel, DEFAULT_FUEL_TYPE)

        # KBChaCha doesn't provide HP, so we need to ask the user
        bot.delete_message(message.chat.id, processing_message.message_id)

        car_engine_displacement_int = int(car_engine_displacement) if car_engine_displacement else 0
        price_krw = int(car_price) * 10000
        formatted_car_year = f"20{car_year}"

        pending_hp_input[user_id] = {
            "car_engine_displacement": car_engine_displacement_int,
            "price_krw": price_krw,
            "formatted_car_year": formatted_car_year,
            "car_month": car_month,
            "engine_type": kbchacha_fuel_type,
            "car_title": car_title,
            "formatted_mileage": formatted_mileage,
            "formatted_transmission": formatted_transmission,
            "car_photos": car_photos,
            "year": year,
            "month": month,
            "preview_link": preview_link,
            "link": link,
            "car_id": car_id,
        }

        msg = bot.send_message(
            message.chat.id,
            f"🚗 {car_title}\n\n"
            "Для расчёта таможенных платежей введите мощность двигателя (л.с.):\n"
            "(Эту информацию можно найти в техническом паспорте автомобиля)",
        )
        bot.register_next_step_handler(msg, process_hp_input)
        return

    if "web.chutcha.net" in link:
        result = get_car_info(link)

        # Check if parsing failed
        if result is None or isinstance(result, str):  # get_car_info returns error string for Chutcha
            bot.delete_message(message.chat.id, processing_message.message_id)
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "Попробовать ещё раз",
                    callback_data="calculate_another",
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "Связаться с менеджером", url="https://t.me/DeyTrading6"
                )
            )
            bot.send_message(
                message.chat.id,
                "❌ Не удалось загрузить данные автомобиля с Chutcha.\n\n"
                "Пожалуйста, попробуйте другой автомобиль или свяжитесь с менеджером.",
                reply_markup=keyboard,
            )
            return

        car_title = result["name"]

        month = result["year"]
        year = result["month"]

        # Очищаем объём двигателя от "cc"
        car_engine_displacement = re.sub(r"\D+", "", result["engine_volume"])

        # Преобразуем цену из формата "3,450만원 / 월 62만원"
        car_price = result["car_price"]

        # Форматируем дату
        formatted_car_date = (
            f"01{car_month}{car_year[-2:]}"
            if car_year != "Не найдено"
            else "Не найдено"
        )

        # Форматируем пробег
        formatted_mileage = format_number(result["mileage"]) + " км"

        # Определяем КПП
        formatted_transmission = (
            "Автомат" if "오토" in result["transmission"] else "Механика"
        )

        # Получаем фотографии автомобиля
        car_photos = result["images"]

        preview_link = f"https://web.chutcha.net/bmc/detail/{car_id}"

        own_car_insurance_payments = result["insurance_claims"]["own_damage_total"]
        other_car_insurance_payments = result["insurance_claims"]["other_damage_total"]

        # Get fuel type from Chutcha data
        car_fuel = result.get("fuel", "")
        chutcha_fuel_type = FUEL_TYPE_MAPPING.get(car_fuel, DEFAULT_FUEL_TYPE)

        # Chutcha doesn't provide HP, so we need to ask the user
        bot.delete_message(message.chat.id, processing_message.message_id)

        car_engine_displacement_int = int(car_engine_displacement) if car_engine_displacement else 0
        # For Chutcha, car_price is already in KRW (plain_price)
        price_krw = int(car_price) * 10000
        formatted_car_year = f"20{year}"

        pending_hp_input[user_id] = {
            "car_engine_displacement": car_engine_displacement_int,
            "price_krw": price_krw,
            "formatted_car_year": formatted_car_year,
            "car_month": month,
            "engine_type": chutcha_fuel_type,
            "car_title": car_title,
            "formatted_mileage": formatted_mileage,
            "formatted_transmission": formatted_transmission,
            "car_photos": car_photos,
            "year": year,
            "month": month,
            "preview_link": preview_link,
            "link": link,
            "car_id": car_id,
            "own_car_insurance_payments": own_car_insurance_payments,
            "other_car_insurance_payments": other_car_insurance_payments,
        }

        msg = bot.send_message(
            message.chat.id,
            f"🚗 {car_title}\n\n"
            "Для расчёта таможенных платежей введите мощность двигателя (л.с.):\n"
            "(Эту информацию можно найти в техническом паспорте автомобиля)",
        )
        bot.register_next_step_handler(msg, process_hp_input)
        return

    if not car_price and car_engine_displacement and formatted_car_date:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "Написать менеджеру", url="https://t.me/DeyTrading6"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Рассчитать стоимость другого автомобиля",
                callback_data="calculate_another",
            )
        )
        bot.send_message(
            message.chat.id, "Ошибка", parse_mode="Markdown", reply_markup=keyboard
        )
        bot.delete_message(message.chat.id, processing_message.message_id)
        return

    if car_price and car_engine_displacement and formatted_car_date:
        car_engine_displacement = int(car_engine_displacement)

        # Форматирование данных
        formatted_car_year = f"20{car_year}"
        engine_volume_formatted = f"{format_number(car_engine_displacement)} cc"

        age = calculate_age(int(formatted_car_year), car_month)

        age_formatted = (
            "до 3 лет"
            if age == "0-3"
            else (
                "от 3 до 5 лет"
                if age == "3-5"
                else "от 5 до 7 лет" if age == "5-7" else "от 7 лет"
            )
        )

        # Конвертируем стоимость авто в рубли
        price_krw = int(car_price) * 10000
        price_usd = price_krw / usd_to_krw_rate
        price_rub = price_usd * usd_to_rub_rate

        print(car_engine_displacement)
        print(price_krw)
        print(int(formatted_car_year))
        print(car_month)

        # Check if we can use pan-auto pre-calculated customs values (Encar only)
        if "fem.encar.com" in link and use_panauto_customs and panauto_data:
            costs_rub = panauto_data.get("costs", {}).get("RUB", {})
            customs_fee = int(costs_rub.get("clearanceCost", 0))
            customs_duty = int(costs_rub.get("customsDuty", 0))
            recycling_fee = int(costs_rub.get("utilizationFee", 0))
            print(f"Using pan-auto customs: fee={customs_fee}, duty={customs_duty}, recycling={recycling_fee}")
        else:
            # Use calcus.ru API with HP from pan-auto (for Encar) or ask user (handled earlier)
            hp_for_customs = panauto_hp if ("fem.encar.com" in link and panauto_hp) else 1

            response = get_customs_fees(
                car_engine_displacement,
                price_krw,
                int(formatted_car_year),
                car_month,
                hp_for_customs,
                engine_type=panauto_fuel_type if "fem.encar.com" in link else DEFAULT_FUEL_TYPE,
            )

            if response is None:
                bot.delete_message(message.chat.id, processing_message.message_id)
                bot.send_message(
                    message.chat.id,
                    "❌ Не удалось рассчитать таможенные платежи. Попробуйте позже."
                )
                return

            # Таможенный сбор
            customs_fee = clean_number(response["sbor"])
            customs_duty = clean_number(response["tax"])
            recycling_fee = clean_number(response["util"])

        # Расчет итоговой стоимости автомобиля в рублях
        total_cost = (
            price_rub
            + ((1400000 / usd_to_krw_rate) * usd_to_rub_rate)
            + ((300000 / usd_to_krw_rate) * usd_to_rub_rate)
            + ((440000 / usd_to_krw_rate) * usd_to_rub_rate)
            + 100000
            + customs_fee
            + customs_duty
            + recycling_fee
            + 13000
            + 200000
        )

        total_cost_krw = (
            price_krw
            + 300000
            + 440000
            + (1400000 / usd_to_krw_rate)
            + (100000 / usd_to_rub_rate) * usd_to_krw_rate
            + (customs_fee / usd_to_rub_rate) * usd_to_krw_rate
            + (customs_duty / usd_to_rub_rate) * usd_to_krw_rate
            + (recycling_fee / usd_to_rub_rate) * usd_to_krw_rate
            + (13000 / usd_to_rub_rate) * usd_to_krw_rate
            + (200000 / usd_to_rub_rate) * usd_to_krw_rate
        )

        total_cost_usd = (
            price_usd
            + (1400000 / usd_to_krw_rate)
            + (300000 / usd_to_krw_rate)
            + (440000 / usd_to_krw_rate)
            + (100000 / usd_to_rub_rate)
            + (customs_fee / usd_to_rub_rate)
            + (customs_duty / usd_to_rub_rate)
            + (recycling_fee / usd_to_rub_rate)
            + (13000 / usd_to_rub_rate)
            + (200000 / usd_to_rub_rate)
        )

        car_data["total_cost_usd"] = total_cost_usd
        car_data["total_cost_krw"] = total_cost_krw
        car_data["total_cost_rub"] = total_cost

        car_data["company_fees_usd"] = 0
        car_data["company_fees_krw"] = 0
        car_data["company_fees_rub"] = 0

        car_data["car_price_krw"] = price_krw
        car_data["car_price_usd"] = price_usd
        car_data["car_price_rub"] = price_rub

        car_data["dealer_korea_usd"] = 440000 / usd_to_krw_rate
        car_data["dealer_korea_krw"] = 440000
        car_data["dealer_korea_rub"] = (440000 / usd_to_krw_rate) * usd_to_rub_rate

        car_data["delivery_korea_usd"] = 100000 / usd_to_krw_rate
        car_data["delivery_korea_krw"] = 100000
        car_data["delivery_korea_rub"] = (100000 / usd_to_krw_rate) * usd_to_rub_rate

        car_data["transfer_korea_usd"] = 350000 / usd_to_krw_rate
        car_data["transfer_korea_krw"] = 350000
        car_data["transfer_korea_rub"] = (350000 / usd_to_krw_rate) * usd_to_rub_rate

        car_data["freight_korea_usd"] = 300000 / usd_to_krw_rate
        car_data["freight_korea_krw"] = 300000
        car_data["freight_korea_rub"] = (300000 / usd_to_krw_rate) * usd_to_rub_rate

        car_data["korea_total_usd"] = (
            (50000 / usd_to_rub_rate)
            + (440000 / usd_to_krw_rate)
            + (100000 / usd_to_krw_rate)
            + (350000 / usd_to_krw_rate)
            + (600)
        )

        car_data["korea_total_krw"] = (
            ((50000 / usd_to_rub_rate) * usd_to_krw_rate)
            + (440000)
            + (100000)
            + 350000
            + (600 * usd_to_krw_rate)
        )

        car_data["korea_total_rub"] = (
            (50000)
            + ((440000 / usd_to_krw_rate) * usd_to_rub_rate)
            + ((100000 / usd_to_krw_rate) * usd_to_rub_rate)
            + ((350000 / usd_to_krw_rate) * usd_to_rub_rate)
            + (600 * usd_to_rub_rate)
        )

        car_data["korea_total_plus_car_usd"] = (
            (50000 / usd_to_rub_rate)
            + (price_usd)
            + (440000 / usd_to_krw_rate)
            + (100000 / usd_to_krw_rate)
            + (350000 / usd_to_krw_rate)
            + (600)
        )
        car_data["korea_total_plus_car_krw"] = (
            ((50000 / usd_to_rub_rate) * usd_to_krw_rate)
            + (price_krw)
            + (440000)
            + (100000)
            + 350000
            + (600 * usd_to_krw_rate)
        )
        car_data["korea_total_plus_car_rub"] = (
            (50000)
            + (price_rub)
            + ((440000 / usd_to_krw_rate) * usd_to_rub_rate)
            + ((100000 / usd_to_krw_rate) * usd_to_rub_rate)
            + ((350000 / usd_to_krw_rate) * usd_to_rub_rate)
            + (600 * usd_to_rub_rate)
        )

        car_data["vladivostok_parom_krw"] = 1400000
        car_data["vladivostok_parom_usd"] = 1400000 / usd_to_krw_rate
        car_data["vladivostok_parom_rub"] = (
            1400000 / usd_to_krw_rate
        ) * usd_to_rub_rate

        # Расходы Россия
        car_data["customs_duty_usd"] = customs_duty / usd_to_rub_rate
        car_data["customs_duty_krw"] = (
            customs_duty / usd_to_rub_rate
        ) * usd_to_krw_rate
        car_data["customs_duty_rub"] = customs_duty

        car_data["customs_fee_usd"] = customs_fee / usd_to_rub_rate
        car_data["customs_fee_krw"] = (customs_fee / usd_to_rub_rate) * usd_to_krw_rate
        car_data["customs_fee_rub"] = customs_fee

        car_data["util_fee_usd"] = recycling_fee / usd_to_rub_rate
        car_data["util_fee_krw"] = (recycling_fee / usd_to_rub_rate) * usd_to_krw_rate
        car_data["util_fee_rub"] = recycling_fee

        car_data["broker_russia_usd"] = 100000 / usd_to_rub_rate
        car_data["broker_russia_krw"] = (100000 / usd_to_rub_rate) * usd_to_krw_rate
        car_data["broker_russia_rub"] = 100000

        car_data["moscow_transporter_usd"] = 200000 / usd_to_rub_rate
        car_data["moscow_transporter_krw"] = (
            200000 / usd_to_rub_rate
        ) * usd_to_krw_rate
        car_data["moscow_transporter_rub"] = 200000

        car_data["vladivostok_transfer_usd"] = 13000 / usd_to_rub_rate
        car_data["vladivostok_transfer_krw"] = (
            13000 / usd_to_rub_rate
        ) * usdt_to_krw_rate
        car_data["vladivostok_transfer_rub"] = 13000

        car_data["svh_russia_usd"] = 50000 / usd_to_rub_rate
        car_data["svh_russia_krw"] = (50000 / usd_to_rub_rate) * usd_to_krw_rate
        car_data["svh_russia_rub"] = 50000

        car_data["lab_russia_usd"] = 30000 / usd_to_rub_rate
        car_data["lab_russia_krw"] = (30000 / usd_to_rub_rate) * usd_to_krw_rate
        car_data["lab_russia_rub"] = 30000

        car_data["perm_registration_russia_usd"] = 8000 / usd_to_rub_rate
        car_data["perm_registration_russia_krw"] = (
            8000 / usd_to_rub_rate
        ) * usd_to_krw_rate
        car_data["perm_registration_russia_rub"] = 8000

        car_data["russia_total_usd"] = (
            (customs_duty / usd_to_rub_rate)
            + (customs_fee / usd_to_rub_rate)
            + (recycling_fee / usd_to_rub_rate)
            + (346)
            + (50000 / usd_to_rub_rate)
            + (8000 / usd_to_rub_rate)
        )
        car_data["russia_total_krw"] = (
            ((customs_duty / usd_to_rub_rate) * usd_to_krw_rate)
            + ((customs_fee / usd_to_rub_rate) * usd_to_krw_rate)
            + ((recycling_fee / usd_to_rub_rate) * usd_to_krw_rate)
            + (346 * usd_to_krw_rate)
            + ((50000 / usd_to_rub_rate) * usd_to_krw_rate)
            + ((8000 / usd_to_rub_rate) * usd_to_krw_rate)
        )
        car_data["russia_total_rub"] = (
            customs_duty
            + customs_fee
            + recycling_fee
            + (346 * usd_to_rub_rate)
            + 50000
            + 8000
        )

        car_insurance_payments_chutcha = ""
        if "web.chutcha.net" in link:
            own_insurance_text = (
                f"₩{format_number(own_car_insurance_payments)}"
                if isinstance(own_car_insurance_payments, int)
                else "Нет"
            )
            other_insurance_text = (
                f"₩{format_number(other_car_insurance_payments)}"
                if isinstance(other_car_insurance_payments, int)
                else "Нет"
            )

            car_insurance_payments_chutcha = (
                f"Страховые выплаты по данному автомобилю:\n{own_insurance_text}\n"
                f"Страховые выплаты другому автомобилю:\n{other_insurance_text}\n\n"
            )

        # Формирование сообщения результата
        result_message = (
            f"{car_title}\n\n"
            f"Возраст: {age_formatted} (дата регистрации: {month}/{year})\n"
            f"Пробег: {formatted_mileage}\n"
            f"Объём двигателя: {engine_volume_formatted}\n"
            f"КПП: {formatted_transmission}\n\n"
            f"Стоимость автомобиля в Корее: ₩{format_number(price_krw)}\n"
            f"Стоимость автомобиля под ключ до Владивостока: \n<b>${format_number(total_cost_usd)} </b> | <b>₩{format_number(total_cost_krw)} </b> | <b>{format_number(total_cost)} ₽</b>\n\n"
            f"{car_insurance_payments_chutcha}"
            f"💵 <b>Курс USDT к Воне: ₩{format_number(usdt_to_krw_rate)}</b>\n\n"
            f"🔗 <a href='{preview_link}'>Ссылка на автомобиль</a>\n\n"
            "Если данное авто попадает под санкции, пожалуйста уточните возможность отправки в вашу страну у наших менеджеров:\n\n"
            f"▪️ +82-10-8855-0386 (Андрей)\n"
            # f"▪️ +82 10-5128-8082 (Александр) \n\n"
            "🔗 <a href='https://t.me/dey_trading'>Официальный телеграм канал</a>\n"
        )

        # Клавиатура с дальнейшими действиями
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("Детали расчёта", callback_data="detail")
        )

        # Кнопка для добавления в избранное
        keyboard.add(
            types.InlineKeyboardButton(
                "⭐ Добавить в избранное",
                callback_data=f"add_favorite_{car_id_external}",
            )
        )

        if "fem.encar.com" in link:
            keyboard.add(
                types.InlineKeyboardButton(
                    "Технический Отчёт об Автомобиле", callback_data="technical_card"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "Выплаты по ДТП",
                    callback_data="technical_report",
                )
            )
        keyboard.add(
            types.InlineKeyboardButton(
                "Написать менеджеру", url="https://t.me/DeyTrading6"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Расчёт другого автомобиля",
                callback_data="calculate_another",
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Главное меню",
                callback_data="main_menu",
            )
        )

        # Отправляем до 10 фотографий
        media_group = []
        for photo_url in sorted(car_photos):
            try:
                response = requests.get(photo_url)
                if response.status_code == 200:
                    photo = BytesIO(response.content)  # Загружаем фото в память
                    media_group.append(
                        types.InputMediaPhoto(photo)
                    )  # Добавляем в список

                    # Если набрали 10 фото, отправляем альбом
                    if len(media_group) == 10:
                        bot.send_media_group(message.chat.id, media_group)
                        media_group.clear()  # Очищаем список для следующей группы
                else:
                    print(f"Ошибка загрузки фото: {photo_url} - {response.status_code}")
            except Exception as e:
                print(f"Ошибка при обработке фото {photo_url}: {e}")

        # Отправка оставшихся фото, если их меньше 10
        if media_group:
            bot.send_media_group(message.chat.id, media_group)

        car_data["car_id"] = car_id
        car_data["name"] = car_title
        car_data["images"] = car_photos if isinstance(car_photos, list) else []
        car_data["link"] = preview_link
        car_data["year"] = year
        car_data["month"] = month
        car_data["mileage"] = formatted_mileage
        car_data["engine_volume"] = car_engine_displacement
        car_data["transmission"] = formatted_transmission
        car_data["car_price"] = price_krw
        car_data["user_name"] = message.from_user.username
        car_data["first_name"] = message.from_user.first_name
        car_data["last_name"] = message.from_user.last_name

        bot.send_message(
            message.chat.id,
            result_message,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        bot.delete_message(
            message.chat.id, processing_message.message_id
        )  # Удаляем сообщение о передаче данных в обработку

    else:
        send_error_message(
            message,
            "🚫 Произошла ошибка при получении данных. Проверьте ссылку и попробуйте снова.",
        )
        bot.delete_message(message.chat.id, processing_message.message_id)


# Function to get insurance total
def get_insurance_total():
    global car_id_external, vehicle_no, vehicle_id

    print_message("[ЗАПРОС] ТЕХНИЧЕСКИЙ ОТЧËТ ОБ АВТОМОБИЛЕ")

    formatted_vehicle_no = urllib.parse.quote(str(vehicle_no).strip())
    url = f"https://api.encar.com/v1/readside/record/vehicle/{str(vehicle_id)}/open?vehicleNo={formatted_vehicle_no}"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": "http://www.encar.com/",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
        }

        response = requests.get(url, headers, timeout=10)

        # Check status code before parsing
        if response.status_code != 200:
            logging.error(f"Encar insurance API returned status {response.status_code}")
            return ["", ""]

        json_response = response.json()

        # Форматируем данные
        damage_to_my_car = json_response["myAccidentCost"]
        damage_to_other_car = json_response["otherAccidentCost"]

        print(
            f"Выплаты по представленному автомобилю: {format_number(damage_to_my_car)}"
        )
        print(f"Выплаты другому автомобилю: {format_number(damage_to_other_car)}")

        return [format_number(damage_to_my_car), format_number(damage_to_other_car)]

    except requests.exceptions.Timeout:
        logging.error("Timeout fetching insurance data from Encar")
        return ["", ""]
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error fetching insurance data: {e}")
        return ["", ""]
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error for insurance data: {e}")
        return ["", ""]
    except (KeyError, TypeError) as e:
        logging.error(f"Error parsing insurance data: {e}")
        return ["", ""]
    except Exception as e:
        logging.error(f"Unexpected error in get_insurance_total: {e}")
        return ["", ""]


def get_technical_card():
    global vehicle_id

    url = f"https://api.encar.com/v1/readside/inspection/vehicle/{vehicle_id}"

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": "http://www.encar.com/",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            logging.error(f"Technical card API returned status {response.status_code}")
            return "❌ Ошибка: не удалось получить данные. Проверьте ссылку."

        json_response = response.json()

        if not json_response:
            return "❌ Ошибка: не удалось получить данные. Проверьте ссылку."

        master = json_response.get("master", {}).get("detail", {})
        if not master:
            return "❌ Ошибка: данные о транспортном средстве не найдены."

        vehicle_id = json_response.get("vehicleId", "Не указано")
        model_year = master.get("modelYear", "Не указано").strip()
        vin = master.get("vin", "Не указано")
        first_registration_date = master.get("firstRegistrationDate", "Не указано")
        registration_date = master.get("registrationDate", "Не указано")
        mileage = f"{int(master.get('mileage', 0)):,}".replace(",", " ") + " км"
        transmission = master.get("transmissionType", {}).get("title", "Не указано")
        motor_type = master.get("motorType", "Не указано")
        color = master.get("colorType", {}).get("title", "Не указано")
        accident = "❌ Нет" if not master.get("accdient", False) else "⚠️ Да"
        simple_repair = "❌ Нет" if not master.get("simpleRepair", False) else "⚠️ Да"
        waterlog = "❌ Нет" if not master.get("waterlog", False) else "⚠️ Да"
        tuning = "❌ Нет" if not master.get("tuning", False) else "⚠️ Да"
        car_state = master.get("carStateType", {}).get("title", "Не указано")

        # Переводы
        translations = {
            "오토": "Автоматическая",
            "수동": "Механическая",
            "자가보증": "Собственная гарантия",
            "양호": "Хорошее состояние",
            "무채색": "Нейтральный",
            "적정": "В норме",
            "없음": "Нет",
            "누유": "Утечка",
            "불량": "Неисправность",
            "미세누유": "Незначительная утечка",
            "양호": "В хорошем состоянии",
            "주의": "Требует внимания",
            "교환": "Замена",
            "부족": "Недостаточный уровень",
            "정상": "Нормально",
            "작동불량": "Неисправна",
            "소음": "Шум",
            "작동양호": "Работает хорошо",
        }

        def translate(value):
            return translations.get(value, value)

        # Проверка состояния узлов
        inners = json_response.get("inners", [])
        nodes_status = {}

        for inner in inners:
            for child in inner.get("children", []):
                type_code = child.get("type", {}).get("code", "")
                status_type = child.get("statusType")
                status = (
                    translate(status_type.get("title", "Не указано"))
                    if status_type
                    else "Не указано"
                )

                nodes_status[type_code] = status

        output = (
            f"🚗 <b>Основная информация об автомобиле</b>\n"
            f"	•	ID автомобиля: {vehicle_id}\n"
            f"	•	Год выпуска: {model_year}\n"
            f"	•	Дата первой регистрации: {first_registration_date}\n"
            f"	•	Дата регистрации в системе: {registration_date}\n"
            f"	•	VIN: {vin}\n"
            f"	•	Пробег: {mileage}\n"
            f"	•	Тип трансмиссии: {translate(transmission)} ({transmission})\n"
            f"	•	Тип двигателя: {motor_type}\n"
            f"	•	Состояние автомобиля: {translate(car_state)} ({car_state})\n"
            f"	•	Цвет: {translate(color)} ({color})\n"
            f"	•	Тюнинг: {tuning}\n"
            f"	•	Автомобиль попадал в ДТП: {accident}\n"
            f"	•	Были ли простые ремонты: {simple_repair}\n"
            f"	•	Затопление: {waterlog}\n"
            f"\n⸻\n\n"
            f"⚙️ <b>Проверка основных узлов</b>\n"
            f"	•	Двигатель: ✅ {nodes_status.get('s001', 'Не указано')}\n"
            f"	•	Трансмиссия: ✅ {nodes_status.get('s002', 'Не указано')}\n"
            f"	•	Работа двигателя на холостом ходу: ✅ {nodes_status.get('s003', 'Не указано')}\n"
            f"	•	Утечка масла двигателя: {'❌ Нет' if nodes_status.get('s004', '없음') == 'Нет' else '⚠️ Да'} ({nodes_status.get('s004', 'Не указано')})\n"
            f"	•	Уровень масла в двигателе: ✅ {nodes_status.get('s005', 'Не указано')}\n"
            f"	•	Утечка охлаждающей жидкости: {'❌ Нет' if nodes_status.get('s006', '없음') == 'Нет' else '⚠️ Да'} ({nodes_status.get('s006', 'Не указано')})\n"
            f"	•	Уровень охлаждающей жидкости: ✅ {nodes_status.get('s007', 'Не указано')}\n"
            f"	•	Система подачи топлива: ✅ {nodes_status.get('s008', 'Не указано')}\n"
            f"	•	Автоматическая коробка передач: ✅ {nodes_status.get('s009', 'Не указано')}\n"
            f"	•	Утечка масла в АКПП: {'❌ Нет' if nodes_status.get('s010', '없음') == 'Нет' else '⚠️ Да'} ({nodes_status.get('s010', 'Не указано')})\n"
            f"	•	Работа АКПП на холостом ходу: ✅ {nodes_status.get('s011', 'Не указано')}\n"
            f"	•	Система сцепления: ✅ {nodes_status.get('s012', 'Не указано')}\n"
            f"	•	Карданный вал и подшипники: ✅ {nodes_status.get('s013', 'Не указано')}\n"
            f"	•	Редуктор: ✅ {nodes_status.get('s014', 'Не указано')}\n"
        )

        return output

    except requests.exceptions.Timeout:
        logging.error("Timeout fetching technical card from Encar")
        return "❌ Ошибка: превышено время ожидания ответа от сервера."
    except requests.RequestException as e:
        logging.error(f"Request error fetching technical card: {e}")
        return f"❌ Ошибка при получении данных: {e}"
    except json.JSONDecodeError as e:
        logging.error(f"JSON decode error for technical card: {e}")
        return "❌ Ошибка: получен некорректный ответ от сервера."
    except (KeyError, TypeError, AttributeError) as e:
        logging.error(f"Error parsing technical card data: {e}")
        return "❌ Ошибка: не удалось обработать данные о транспортном средстве."
    except Exception as e:
        logging.error(f"Unexpected error in get_technical_card: {e}")
        return f"❌ Непредвиденная ошибка: {e}"


# Callback query handler
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    global car_data, car_id_external, usd_rate

    if call.data.startswith("detail"):
        print_message("[ЗАПРОС] ДЕТАЛИЗАЦИЯ РАСЧËТА")

        detail_message = (
            f"<i>ПЕРВАЯ ЧАСТЬ ОПЛАТЫ (КОРЕЯ)</i>:\n\n"
            f"Стоимость автомобиля:\n<b>${format_number(car_data['car_price_usd'])}</b> | <b>₩{format_number(car_data['car_price_krw'])}</b> | <b>{format_number(car_data['car_price_rub'])} ₽</b>\n\n"
            f"Услуги фирмы (поиск и подбор авто, документация, 2 осмотра):\n<b>$0</b> | <b>₩0</b> | <b>0 ₽</b>\n\n"
            f"Фрахт (доставка автомобиля на базу, оплата судна):\n${format_number(car_data['vladivostok_parom_usd'])} | ₩{format_number(car_data['vladivostok_parom_krw'])} | {format_number(car_data['vladivostok_parom_rub'])} ₽\n\n"
            f"Доставка до порта г. Пусан:\n<b>${format_number(car_data['freight_korea_usd'])}</b> | <b>₩{format_number(car_data['freight_korea_krw'])}</b> | <b>{format_number(car_data['freight_korea_rub'])} ₽</b>\n\n\n"
            f"Диллерский сбор:\n<b>${format_number(car_data['dealer_korea_usd'])}</b> | <b>₩{format_number(car_data['dealer_korea_krw'])}</b> | <b>{format_number(car_data['dealer_korea_rub'])} ₽</b>\n\n"
            f"<i>ВТОРАЯ ЧАСТЬ ОПЛАТЫ (РОССИЯ)</i>:\n\n"
            f"Декларант:\n<b>${format_number(car_data['broker_russia_usd'])}</b> | <b>₩{format_number(car_data['broker_russia_krw'])}</b> | <b>{format_number(car_data['broker_russia_rub'])} ₽</b>\n\n\n"
            f"Единая таможенная ставка:\n<b>${format_number(car_data['customs_duty_usd'])}</b> | <b>₩{format_number(car_data['customs_duty_krw'])}</b> | <b>{format_number(car_data['customs_duty_rub'])} ₽</b>\n\n"
            f"Таможенное оформление:\n<b>${format_number(car_data['customs_fee_usd'])}</b> | <b>₩{format_number(car_data['customs_fee_krw'])}</b> | <b>{format_number(car_data['customs_fee_rub'])} ₽</b>\n\n"
            f"Утилизационный сбор:\n<b>${format_number(car_data['util_fee_usd'])}</b> | <b>₩{format_number(car_data['util_fee_krw'])}</b> | <b>{format_number(car_data['util_fee_rub'])} ₽</b>\n\n\n"
            f"Перегон во Владивостоке:\n<b>${format_number(car_data['vladivostok_transfer_usd'])}</b> | <b>₩{format_number(car_data['vladivostok_transfer_krw'])}</b> | <b>{format_number(car_data['vladivostok_transfer_rub'])} ₽</b>\n\n"
            f"Автовоз до Москвы:\n<b>${format_number(car_data['moscow_transporter_usd'])}</b> | <b>₩{format_number(car_data['moscow_transporter_krw'])}</b> | <b>{format_number(car_data['moscow_transporter_rub'])} ₽</b>\n\n"
            f"Итого под ключ: \n<b>${format_number(car_data['total_cost_usd'])}</b> | <b>₩{format_number(car_data['total_cost_krw'])}</b> | <b>{format_number(car_data['total_cost_rub'])} ₽</b>\n\n"
            f"<b>Доставку до вашего города уточняйте у менеджеров:</b>\n"
            f"▪️ +82-10-8855-0386 (Андрей)\n"
            # f"▪️ +82 10-5128-8082 (Александр)\n\n"
        )

        # Inline buttons for further actions
        keyboard = types.InlineKeyboardMarkup()

        if call.data.startswith("detail_manual"):
            keyboard.add(
                types.InlineKeyboardButton(
                    "Рассчитать стоимость другого автомобиля",
                    callback_data="calculate_another_manual",
                )
            )
        else:
            keyboard.add(
                types.InlineKeyboardButton(
                    "Рассчитать стоимость другого автомобиля",
                    callback_data="calculate_another",
                )
            )

        keyboard.add(
            types.InlineKeyboardButton("Главное меню", callback_data="main_menu")
        )

        bot.send_message(
            call.message.chat.id,
            detail_message,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    elif call.data == "technical_card":
        print_message("[ЗАПРОС] ТЕХНИЧЕСКАЯ ОТЧËТ ОБ АВТОМОБИЛЕ")

        technical_card_output = get_technical_card()

        bot.send_message(
            call.message.chat.id,
            "Запрашиваю отчёт по автомобилю. Пожалуйста подождите ⏳",
        )

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "Рассчитать стоимость другого автомобиля",
                callback_data="calculate_another",
            )
        )
        keyboard.add(
            types.InlineKeyboardButton("Главное меню", callback_data="main_menu")
        )
        # keyboard.add(
        #     types.InlineKeyboardButton(
        #         "Связаться с менеджером", url="https://t.me/DeyTrading6"
        #     )
        # )

        bot.send_message(
            call.message.chat.id,
            technical_card_output,
            parse_mode="HTML",
            reply_markup=keyboard,
        )

    elif call.data == "technical_report":
        bot.send_message(
            call.message.chat.id,
            "Запрашиваю отчёт по ДТП. Пожалуйста подождите ⏳",
        )

        # Retrieve insurance information
        insurance_info = get_insurance_total()

        # Проверка на наличие ошибки
        if (
            insurance_info is None
            or "Нет данных" in insurance_info[0]
            or "Нет данных" in insurance_info[1]
        ):
            error_message = (
                "Не удалось получить данные о страховых выплатах. \n\n"
                f'<a href="https://fem.encar.com/cars/report/accident/{car_id_external}">🔗 Посмотреть страховую историю вручную 🔗</a>\n\n\n'
                f"<b>Найдите две строки:</b>\n\n"
                f"보험사고 이력 (내차 피해) - Выплаты по представленному автомобилю\n"
                f"보험사고 이력 (타차 가해) - Выплаты другим участникам ДТП"
            )

            # Inline buttons for further actions
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "Рассчитать стоимость другого автомобиля",
                    callback_data="calculate_another",
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "Связаться с менеджером", url="https://t.me/DeyTrading6"
                )
            )

            # Отправка сообщения об ошибке
            bot.send_message(
                call.message.chat.id,
                error_message,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            current_car_insurance_payments = (
                "0" if len(insurance_info[0]) == 0 else insurance_info[0]
            )
            other_car_insurance_payments = (
                "0" if len(insurance_info[1]) == 0 else insurance_info[1]
            )

            # Construct the message for the technical report
            tech_report_message = (
                f"Страховые выплаты по представленному автомобилю: \n<b>{current_car_insurance_payments} ₩</b>\n\n"
                f"Страховые выплаты другим участникам ДТП: \n<b>{other_car_insurance_payments} ₩</b>\n\n"
                f'<a href="https://fem.encar.com/cars/report/inspect/{car_id_external}">🔗 Ссылка на схему повреждений кузовных элементов 🔗</a>'
            )

            # Inline buttons for further actions
            keyboard = types.InlineKeyboardMarkup()
            keyboard.add(
                types.InlineKeyboardButton(
                    "Рассчитать стоимость другого автомобиля",
                    callback_data="calculate_another",
                )
            )
            keyboard.add(
                types.InlineKeyboardButton(
                    "Связаться с менеджером", url="https://t.me/DeyTrading6"
                )
            )
            keyboard.add(
                types.InlineKeyboardButton("Главное меню", callback_data="main_menu")
            )

            bot.send_message(
                call.message.chat.id,
                tech_report_message,
                parse_mode="HTML",
                reply_markup=keyboard,
            )

    elif call.data == "calculate_another":
        bot.send_message(
            call.message.chat.id,
            "Пожалуйста, введите ссылку на автомобиль с сайта (encar.com, kbchachacha.com, web.chutcha.net)",
        )

    elif call.data == "calculate_another_manual":
        msg = bot.send_message(
            call.message.chat.id,
            "Выберите возраст автомобиля",
        )
        bot.register_next_step_handler(msg, process_car_age)

    elif call.data == "main_menu":
        bot.send_message(call.message.chat.id, "Главное меню", reply_markup=main_menu())


def process_car_age(message):
    user_input = message.text.strip()
    user_id = message.chat.id

    # Проверяем ввод
    age_mapping = {
        "До 3 лет": "0-3",
        "От 3 до 5 лет": "3-5",
        "От 5 до 7 лет": "5-7",
        "Более 7 лет": "7-0",
    }

    if user_input not in age_mapping:
        bot.send_message(message.chat.id, "Пожалуйста, выберите возраст из списка.")
        return

    # Инициализируем словарь для пользователя, если его нет
    if user_id not in user_data:
        user_data[user_id] = {}

    # Сохраняем возраст авто
    user_data[user_id]["car_age"] = age_mapping[user_input]

    # Запрашиваем объем двигателя
    bot.send_message(
        message.chat.id,
        "Введите объем двигателя в см³ (например, 1998):",
    )
    bot.register_next_step_handler(message, process_engine_volume)


def process_engine_volume(message):
    user_input = message.text.strip()

    # Проверяем, что введено число
    if not user_input.isdigit():
        bot.send_message(
            message.chat.id, "Пожалуйста, введите корректный объем двигателя в см³."
        )
        bot.register_next_step_handler(message, process_engine_volume)
        return

    # Сохраняем объем двигателя
    user_data[message.chat.id]["engine_volume"] = int(user_input)

    # Запрашиваем мощность двигателя
    bot.send_message(
        message.chat.id,
        "Введите мощность двигателя в л.с. (например, 150):",
    )
    bot.register_next_step_handler(message, process_hp_manual)


def process_hp_manual(message):
    """Process HP input for manual calculation flow."""
    user_input = message.text.strip()
    user_id = message.chat.id

    # Проверяем, что введено число
    if not user_input.isdigit() or int(user_input) <= 0:
        bot.send_message(
            message.chat.id,
            "Пожалуйста, введите корректную мощность двигателя в л.с. (положительное число):"
        )
        bot.register_next_step_handler(message, process_hp_manual)
        return

    # Сохраняем мощность двигателя
    user_data[user_id]["engine_hp"] = int(user_input)

    # Запрашиваем стоимость авто
    bot.send_message(
        message.chat.id,
        "Введите стоимость автомобиля в корейских вонах (например, 15000000):",
    )
    bot.register_next_step_handler(message, process_car_price)


def process_car_price(message):
    global usd_to_krw_rate, usd_to_rub_rate

    user_input = message.text.strip()
    user_id = message.chat.id

    # Добавляем пользователя в базу данных
    user_data_db = {
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "last_name": message.from_user.last_name,
        "phone_number": user_contacts.get(message.from_user.id, None),
    }
    add_or_update_user(user_data_db)

    # Проверяем, что введено число
    if not user_input.isdigit():
        bot.send_message(
            message.chat.id,
            "Пожалуйста, введите корректную стоимость автомобиля в вонах.",
        )
        bot.register_next_step_handler(message, process_car_price)
        return

    # Инициализируем словарь для пользователя, если его нет
    if user_id not in user_data:
        user_data[user_id] = {}

    # Проверяем, есть ли нужные ключи
    if "car_age" not in user_data[user_id] or "engine_volume" not in user_data[user_id] or "engine_hp" not in user_data[user_id]:
        bot.send_message(
            message.chat.id,
            "Произошла ошибка. Пожалуйста, начните расчёт заново, выбрав 'Ручной расчёт' из меню.",
        )
        return

    # Сохраняем стоимость автомобиля
    user_data[user_id]["car_price_krw"] = int(user_input)

    # Извлекаем данные пользователя
    if message.chat.id not in user_data:
        user_data[message.chat.id] = {}

    age_group = user_data[user_id]["car_age"]
    engine_volume = user_data[user_id]["engine_volume"]
    engine_hp = user_data[user_id]["engine_hp"]
    car_price_krw = user_data[user_id]["car_price_krw"]

    # Конвертируем стоимость автомобиля в USD и RUB
    price_krw = int(car_price_krw)
    price_usd = price_krw / usd_to_krw_rate
    price_rub = price_usd * usd_to_rub_rate

    response = get_customs_fees_manual(
        engine_volume,
        price_krw,
        age_group,
        engine_hp,
        engine_type=DEFAULT_FUEL_TYPE,
    )

    if response is None:
        bot.send_message(
            message.chat.id,
            "❌ Не удалось рассчитать таможенные платежи. Попробуйте позже."
        )
        return

    # Таможенный сбор
    customs_fee = clean_number(response["sbor"])
    customs_duty = clean_number(response["tax"])
    recycling_fee = clean_number(response["util"])

    # Расчет итоговой стоимости автомобиля в рублях
    total_cost = (
        price_rub
        + ((1400000 / usd_to_krw_rate) * usd_to_rub_rate)
        + ((300000 / usd_to_krw_rate) * usd_to_rub_rate)
        + ((440000 / usd_to_krw_rate) * usd_to_rub_rate)
        + 100000
        + customs_fee
        + customs_duty
        + recycling_fee
        + 13000
        + 200000
    )

    total_cost_krw = (
        price_krw
        + 300000
        + 440000
        + (1400000 / usd_to_krw_rate)
        + (100000 / usd_to_rub_rate) * usd_to_krw_rate
        + (customs_fee / usd_to_rub_rate) * usd_to_krw_rate
        + (customs_duty / usd_to_rub_rate) * usd_to_krw_rate
        + (recycling_fee / usd_to_rub_rate) * usd_to_krw_rate
        + (13000 / usd_to_rub_rate) * usd_to_krw_rate
        + (200000 / usd_to_rub_rate) * usd_to_krw_rate
    )

    total_cost_usd = (
        price_usd
        + (1400000 / usd_to_krw_rate)
        + (300000 / usd_to_krw_rate)
        + (440000 / usd_to_krw_rate)
        + (100000 / usd_to_rub_rate)
        + (customs_fee / usd_to_rub_rate)
        + (customs_duty / usd_to_rub_rate)
        + (recycling_fee / usd_to_rub_rate)
        + (13000 / usd_to_rub_rate)
        + (200000 / usd_to_rub_rate)
    )

    car_data["total_cost_usd"] = total_cost_usd
    car_data["total_cost_krw"] = total_cost_krw
    car_data["total_cost_rub"] = total_cost

    car_data["company_fees_usd"] = 0
    car_data["company_fees_krw"] = 0
    car_data["company_fees_rub"] = 0

    car_data["car_price_krw"] = price_krw
    car_data["car_price_usd"] = price_usd
    car_data["car_price_rub"] = price_rub

    car_data["dealer_korea_usd"] = 440000 / usd_to_krw_rate
    car_data["dealer_korea_krw"] = 440000
    car_data["dealer_korea_rub"] = (440000 / usd_to_krw_rate) * usd_to_rub_rate

    car_data["delivery_korea_usd"] = 100000 / usd_to_krw_rate
    car_data["delivery_korea_krw"] = 100000
    car_data["delivery_korea_rub"] = (100000 / usd_to_krw_rate) * usd_to_rub_rate

    car_data["transfer_korea_usd"] = 350000 / usd_to_krw_rate
    car_data["transfer_korea_krw"] = 350000
    car_data["transfer_korea_rub"] = (350000 / usd_to_krw_rate) * usd_to_rub_rate

    car_data["freight_korea_usd"] = 300000 / usd_to_krw_rate
    car_data["freight_korea_krw"] = 300000
    car_data["freight_korea_rub"] = (300000 / usd_to_krw_rate) * usd_to_rub_rate

    car_data["korea_total_usd"] = (
        (50000 / usd_to_rub_rate)
        + (440000 / usd_to_krw_rate)
        + (100000 / usd_to_krw_rate)
        + (350000 / usd_to_krw_rate)
        + (600)
    )

    car_data["korea_total_krw"] = (
        ((50000 / usd_to_rub_rate) * usd_to_krw_rate)
        + (440000)
        + (100000)
        + 350000
        + (600 * usd_to_krw_rate)
    )

    car_data["korea_total_rub"] = (
        (50000)
        + ((440000 / usd_to_krw_rate) * usd_to_rub_rate)
        + ((100000 / usd_to_krw_rate) * usd_to_rub_rate)
        + ((350000 / usd_to_krw_rate) * usd_to_rub_rate)
        + (600 * usd_to_rub_rate)
    )

    car_data["korea_total_plus_car_usd"] = (
        (50000 / usd_to_rub_rate)
        + (price_usd)
        + (440000 / usd_to_krw_rate)
        + (100000 / usd_to_krw_rate)
        + (350000 / usd_to_krw_rate)
        + (600)
    )
    car_data["korea_total_plus_car_krw"] = (
        ((50000 / usd_to_rub_rate) * usd_to_krw_rate)
        + (price_krw)
        + (440000)
        + (100000)
        + 350000
        + (600 * usd_to_krw_rate)
    )
    car_data["korea_total_plus_car_rub"] = (
        (50000)
        + (price_rub)
        + ((440000 / usd_to_krw_rate) * usd_to_rub_rate)
        + ((100000 / usd_to_krw_rate) * usd_to_rub_rate)
        + ((350000 / usd_to_krw_rate) * usd_to_rub_rate)
        + (600 * usd_to_rub_rate)
    )

    car_data["vladivostok_parom_krw"] = 1400000
    car_data["vladivostok_parom_usd"] = 1400000 / usd_to_krw_rate
    car_data["vladivostok_parom_rub"] = (1400000 / usd_to_krw_rate) * usd_to_rub_rate

    # Расходы Россия
    car_data["customs_duty_usd"] = customs_duty / usd_to_rub_rate
    car_data["customs_duty_krw"] = (customs_duty / usd_to_rub_rate) * usd_to_krw_rate
    car_data["customs_duty_rub"] = customs_duty

    car_data["customs_fee_usd"] = customs_fee / usd_to_rub_rate
    car_data["customs_fee_krw"] = (customs_fee / usd_to_rub_rate) * usd_to_krw_rate
    car_data["customs_fee_rub"] = customs_fee

    car_data["util_fee_usd"] = recycling_fee / usd_to_rub_rate
    car_data["util_fee_krw"] = (recycling_fee / usd_to_rub_rate) * usd_to_krw_rate
    car_data["util_fee_rub"] = recycling_fee

    car_data["broker_russia_usd"] = 100000 / usd_to_rub_rate
    car_data["broker_russia_krw"] = (100000 / usd_to_rub_rate) * usd_to_krw_rate
    car_data["broker_russia_rub"] = 100000

    car_data["moscow_transporter_usd"] = 200000 / usd_to_rub_rate
    car_data["moscow_transporter_krw"] = (200000 / usd_to_rub_rate) * usd_to_krw_rate
    car_data["moscow_transporter_rub"] = 200000

    car_data["vladivostok_transfer_usd"] = 13000 / usd_to_rub_rate
    car_data["vladivostok_transfer_krw"] = (13000 / usd_to_rub_rate) * usdt_to_krw_rate
    car_data["vladivostok_transfer_rub"] = 13000

    car_data["svh_russia_usd"] = 50000 / usd_to_rub_rate
    car_data["svh_russia_krw"] = (50000 / usd_to_rub_rate) * usd_to_krw_rate
    car_data["svh_russia_rub"] = 50000

    car_data["lab_russia_usd"] = 30000 / usd_to_rub_rate
    car_data["lab_russia_krw"] = (30000 / usd_to_rub_rate) * usd_to_krw_rate
    car_data["lab_russia_rub"] = 30000

    car_data["perm_registration_russia_usd"] = 8000 / usd_to_rub_rate
    car_data["perm_registration_russia_krw"] = (
        8000 / usd_to_rub_rate
    ) * usd_to_krw_rate
    car_data["perm_registration_russia_rub"] = 8000

    car_data["russia_total_usd"] = (
        (customs_duty / usd_to_rub_rate)
        + (customs_fee / usd_to_rub_rate)
        + (recycling_fee / usd_to_rub_rate)
        + (346)
        + (50000 / usd_to_rub_rate)
        + (8000 / usd_to_rub_rate)
    )
    car_data["russia_total_krw"] = (
        ((customs_duty / usd_to_rub_rate) * usd_to_krw_rate)
        + ((customs_fee / usd_to_rub_rate) * usd_to_krw_rate)
        + ((recycling_fee / usd_to_rub_rate) * usd_to_krw_rate)
        + (346 * usd_to_krw_rate)
        + ((50000 / usd_to_rub_rate) * usd_to_krw_rate)
        + ((8000 / usd_to_rub_rate) * usd_to_krw_rate)
    )
    car_data["russia_total_rub"] = (
        customs_duty
        + customs_fee
        + recycling_fee
        + (346 * usd_to_rub_rate)
        + 50000
        + 8000
    )

    formatted_age_group = (
        "До 3 лет"
        if age_group == "0-3"
        else (
            "От 3 до 5 лет"
            if age_group == "3-5"
            else "От 5 до 7 лет" if age_group == "5-7" else "От 7 лет"
        )
    )

    # Формируем сообщение с расчетом стоимости
    result_message = (
        f"💰 <b>Расчёт стоимости автомобиля</b> 💰\n\n"
        f"📌 Возраст автомобиля: <b>{formatted_age_group}</b>\n"
        f"🚗 Объём двигателя: <b>{format_number(engine_volume)} см³</b>\n"
        f"🐴 Мощность: <b>{engine_hp} л.с.</b>\n\n"
        f"<i>ПЕРВАЯ ЧАСТЬ ОПЛАТЫ (КОРЕЯ)</i>:\n\n"
        f"Стоимость автомобиля:\n<b>${format_number(car_data['car_price_usd'])}</b> | <b>₩{format_number(car_data['car_price_krw'])}</b> | <b>{format_number(car_data['car_price_rub'])} ₽</b>\n\n"
        f"Услуги фирмы (поиск и подбор авто, документация, 2 осмотра):\n<b>$0</b> | <b>₩0</b> | <b>0 ₽</b>\n\n"
        f"Фрахт (доставка автомобиля на базу, оплата судна):\n${format_number(car_data['vladivostok_parom_usd'])} | ₩{format_number(car_data['vladivostok_parom_krw'])} | {format_number(car_data['vladivostok_parom_rub'])} ₽\n\n"
        f"Доставка до порта г. Пусан:\n<b>${format_number(car_data['freight_korea_usd'])}</b> | <b>₩{format_number(car_data['freight_korea_krw'])}</b> | <b>{format_number(car_data['freight_korea_rub'])} ₽</b>\n\n\n"
        f"Диллерский сбор:\n<b>${format_number(car_data['dealer_korea_usd'])}</b> | <b>₩{format_number(car_data['dealer_korea_krw'])}</b> | <b>{format_number(car_data['dealer_korea_rub'])} ₽</b>\n\n"
        f"<i>ВТОРАЯ ЧАСТЬ ОПЛАТЫ (РОССИЯ)</i>:\n\n"
        f"Декларант:\n<b>${format_number(car_data['broker_russia_usd'])}</b> | <b>₩{format_number(car_data['broker_russia_krw'])}</b> | <b>{format_number(car_data['broker_russia_rub'])} ₽</b>\n\n\n"
        f"Единая таможенная ставка:\n<b>${format_number(car_data['customs_duty_usd'])}</b> | <b>₩{format_number(car_data['customs_duty_krw'])}</b> | <b>{format_number(car_data['customs_duty_rub'])} ₽</b>\n\n"
        f"Таможенное оформление:\n<b>${format_number(car_data['customs_fee_usd'])}</b> | <b>₩{format_number(car_data['customs_fee_krw'])}</b> | <b>{format_number(car_data['customs_fee_rub'])} ₽</b>\n\n"
        f"Утилизационный сбор:\n<b>${format_number(car_data['util_fee_usd'])}</b> | <b>₩{format_number(car_data['util_fee_krw'])}</b> | <b>{format_number(car_data['util_fee_rub'])} ₽</b>\n\n\n"
        f"Перегон во Владивостоке:\n<b>${format_number(car_data['vladivostok_transfer_usd'])}</b> | <b>₩{format_number(car_data['vladivostok_transfer_krw'])}</b> | <b>{format_number(car_data['vladivostok_transfer_rub'])} ₽</b>\n\n"
        f"Автовоз до Москвы:\n<b>${format_number(car_data['moscow_transporter_usd'])}</b> | <b>₩{format_number(car_data['moscow_transporter_krw'])}</b> | <b>{format_number(car_data['moscow_transporter_rub'])} ₽</b>\n\n"
        f"Итого под ключ: \n<b>${format_number(car_data['total_cost_usd'])}</b> | <b>₩{format_number(car_data['total_cost_krw'])}</b> | <b>{format_number(car_data['total_cost_rub'])} ₽</b>\n\n"
        f"<b>Доставку до вашего города уточняйте у менеджеров:</b>\n"
        f"▪️ +82-10-8855-0386 (Андрей)\n"
        # f"▪️ +82 10-5128-8082 (Александр)\n\n"
    )

    # Клавиатура с дальнейшими действиями
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "Рассчитать другой автомобиль", callback_data="calculate_another_manual"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "Связаться с менеджером", url="https://t.me/DeyTrading6"
        )
    )
    keyboard.add(types.InlineKeyboardButton("Главное меню", callback_data="main_menu"))

    # Отправляем сообщение пользователю
    bot.send_message(
        message.chat.id,
        result_message,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    # Очищаем данные пользователя после расчета
    del user_data[message.chat.id]


def process_hp_input(message):
    """
    Process user-entered HP value and continue calculation for URL-based flows.
    This handler is used when HP is not available from pan-auto API.
    """
    global car_data, pending_hp_input, usd_to_krw_rate, usd_to_rub_rate, usdt_to_krw_rate

    user_id = message.chat.id
    hp_input = message.text.strip()

    # Validate HP is a number
    if not hp_input.isdigit() or int(hp_input) <= 0:
        bot.send_message(
            user_id,
            "Пожалуйста, введите корректное значение мощности (л.с.) - положительное целое число:"
        )
        bot.register_next_step_handler(message, process_hp_input)
        return

    hp = int(hp_input)

    # Retrieve saved context
    context = pending_hp_input.pop(user_id, None)
    if not context:
        bot.send_message(
            user_id,
            "Ошибка: данные расчёта утеряны. Пожалуйста, начните расчёт заново."
        )
        return

    # Continue calculation with HP value
    continue_calculation_with_hp(user_id, context, hp, message)


def continue_calculation_with_hp(user_id, context, hp, message):
    """
    Resume calculation after user enters HP value.
    Uses calcus.ru API with the provided HP value.
    """
    global car_data, usd_to_krw_rate, usd_to_rub_rate, usdt_to_krw_rate

    # Extract data from context
    car_engine_displacement = context["car_engine_displacement"]
    price_krw = context["price_krw"]
    formatted_car_year = context["formatted_car_year"]
    car_month = context["car_month"]
    engine_type = context.get("engine_type", DEFAULT_FUEL_TYPE)
    car_title = context["car_title"]
    formatted_mileage = context["formatted_mileage"]
    formatted_transmission = context["formatted_transmission"]
    car_photos = context["car_photos"]
    year = context["year"]
    month = context["month"]
    preview_link = context["preview_link"]
    link = context["link"]
    car_id = context["car_id"]
    processing_message_id = context.get("processing_message_id")

    # Calculate prices
    price_usd = price_krw / usd_to_krw_rate
    price_rub = price_usd * usd_to_rub_rate

    # Get customs fees from calcus.ru with HP
    response = get_customs_fees(
        car_engine_displacement,
        price_krw,
        int(formatted_car_year),
        car_month,
        hp,
        engine_type=engine_type,
    )

    if response is None:
        bot.send_message(
            user_id,
            "❌ Не удалось рассчитать таможенные платежи. Попробуйте позже."
        )
        return

    # Таможенный сбор
    customs_fee = clean_number(response["sbor"])
    customs_duty = clean_number(response["tax"])
    recycling_fee = clean_number(response["util"])

    # Calculate age for display
    age = calculate_age(int(formatted_car_year), car_month)
    age_formatted = (
        "до 3 лет"
        if age == "0-3"
        else (
            "от 3 до 5 лет"
            if age == "3-5"
            else "от 5 до 7 лет" if age == "5-7" else "от 7 лет"
        )
    )

    engine_volume_formatted = f"{format_number(car_engine_displacement)} cc"

    # Расчет итоговой стоимости автомобиля в рублях
    total_cost = (
        price_rub
        + ((1400000 / usd_to_krw_rate) * usd_to_rub_rate)
        + ((300000 / usd_to_krw_rate) * usd_to_rub_rate)
        + ((440000 / usd_to_krw_rate) * usd_to_rub_rate)
        + 100000
        + customs_fee
        + customs_duty
        + recycling_fee
        + 13000
        + 200000
    )

    total_cost_krw = (
        price_krw
        + 300000
        + 440000
        + (1400000 / usd_to_krw_rate)
        + (100000 / usd_to_rub_rate) * usd_to_krw_rate
        + (customs_fee / usd_to_rub_rate) * usd_to_krw_rate
        + (customs_duty / usd_to_rub_rate) * usd_to_krw_rate
        + (recycling_fee / usd_to_rub_rate) * usd_to_krw_rate
        + (13000 / usd_to_rub_rate) * usd_to_krw_rate
        + (200000 / usd_to_rub_rate) * usd_to_krw_rate
    )

    total_cost_usd = (
        price_usd
        + (1400000 / usd_to_krw_rate)
        + (300000 / usd_to_krw_rate)
        + (440000 / usd_to_krw_rate)
        + (100000 / usd_to_rub_rate)
        + (customs_fee / usd_to_rub_rate)
        + (customs_duty / usd_to_rub_rate)
        + (recycling_fee / usd_to_rub_rate)
        + (13000 / usd_to_rub_rate)
        + (200000 / usd_to_rub_rate)
    )

    # Update car_data with all calculated values
    car_data["total_cost_usd"] = total_cost_usd
    car_data["total_cost_krw"] = total_cost_krw
    car_data["total_cost_rub"] = total_cost

    car_data["company_fees_usd"] = 0
    car_data["company_fees_krw"] = 0
    car_data["company_fees_rub"] = 0

    car_data["car_price_krw"] = price_krw
    car_data["car_price_usd"] = price_usd
    car_data["car_price_rub"] = price_rub

    car_data["dealer_korea_usd"] = 440000 / usd_to_krw_rate
    car_data["dealer_korea_krw"] = 440000
    car_data["dealer_korea_rub"] = (440000 / usd_to_krw_rate) * usd_to_rub_rate

    car_data["delivery_korea_usd"] = 100000 / usd_to_krw_rate
    car_data["delivery_korea_krw"] = 100000
    car_data["delivery_korea_rub"] = (100000 / usd_to_krw_rate) * usd_to_rub_rate

    car_data["transfer_korea_usd"] = 350000 / usd_to_krw_rate
    car_data["transfer_korea_krw"] = 350000
    car_data["transfer_korea_rub"] = (350000 / usd_to_krw_rate) * usd_to_rub_rate

    car_data["freight_korea_usd"] = 300000 / usd_to_krw_rate
    car_data["freight_korea_krw"] = 300000
    car_data["freight_korea_rub"] = (300000 / usd_to_krw_rate) * usd_to_rub_rate

    car_data["korea_total_usd"] = (
        (50000 / usd_to_rub_rate)
        + (440000 / usd_to_krw_rate)
        + (100000 / usd_to_krw_rate)
        + (350000 / usd_to_krw_rate)
        + (600)
    )

    car_data["korea_total_krw"] = (
        ((50000 / usd_to_rub_rate) * usd_to_krw_rate)
        + (440000)
        + (100000)
        + 350000
        + (600 * usd_to_krw_rate)
    )

    car_data["korea_total_rub"] = (
        (50000)
        + ((440000 / usd_to_krw_rate) * usd_to_rub_rate)
        + ((100000 / usd_to_krw_rate) * usd_to_rub_rate)
        + ((350000 / usd_to_krw_rate) * usd_to_rub_rate)
        + (600 * usd_to_rub_rate)
    )

    car_data["korea_total_plus_car_usd"] = (
        (50000 / usd_to_rub_rate)
        + (price_usd)
        + (440000 / usd_to_krw_rate)
        + (100000 / usd_to_krw_rate)
        + (350000 / usd_to_krw_rate)
        + (600)
    )
    car_data["korea_total_plus_car_krw"] = (
        ((50000 / usd_to_rub_rate) * usd_to_krw_rate)
        + (price_krw)
        + (440000)
        + (100000)
        + 350000
        + (600 * usd_to_krw_rate)
    )
    car_data["korea_total_plus_car_rub"] = (
        (50000)
        + (price_rub)
        + ((440000 / usd_to_krw_rate) * usd_to_rub_rate)
        + ((100000 / usd_to_krw_rate) * usd_to_rub_rate)
        + ((350000 / usd_to_krw_rate) * usd_to_rub_rate)
        + (600 * usd_to_rub_rate)
    )

    car_data["vladivostok_parom_krw"] = 1400000
    car_data["vladivostok_parom_usd"] = 1400000 / usd_to_krw_rate
    car_data["vladivostok_parom_rub"] = (
        1400000 / usd_to_krw_rate
    ) * usd_to_rub_rate

    # Расходы Россия
    car_data["customs_duty_usd"] = customs_duty / usd_to_rub_rate
    car_data["customs_duty_krw"] = (
        customs_duty / usd_to_rub_rate
    ) * usd_to_krw_rate
    car_data["customs_duty_rub"] = customs_duty

    car_data["customs_fee_usd"] = customs_fee / usd_to_rub_rate
    car_data["customs_fee_krw"] = (customs_fee / usd_to_rub_rate) * usd_to_krw_rate
    car_data["customs_fee_rub"] = customs_fee

    car_data["util_fee_usd"] = recycling_fee / usd_to_rub_rate
    car_data["util_fee_krw"] = (recycling_fee / usd_to_rub_rate) * usd_to_krw_rate
    car_data["util_fee_rub"] = recycling_fee

    car_data["broker_russia_usd"] = 100000 / usd_to_rub_rate
    car_data["broker_russia_krw"] = (100000 / usd_to_rub_rate) * usd_to_krw_rate
    car_data["broker_russia_rub"] = 100000

    car_data["moscow_transporter_usd"] = 200000 / usd_to_rub_rate
    car_data["moscow_transporter_krw"] = (
        200000 / usd_to_rub_rate
    ) * usd_to_krw_rate
    car_data["moscow_transporter_rub"] = 200000

    car_data["vladivostok_transfer_usd"] = 13000 / usd_to_rub_rate
    car_data["vladivostok_transfer_krw"] = (
        13000 / usd_to_rub_rate
    ) * usdt_to_krw_rate
    car_data["vladivostok_transfer_rub"] = 13000

    car_data["svh_russia_usd"] = 50000 / usd_to_rub_rate
    car_data["svh_russia_krw"] = (50000 / usd_to_rub_rate) * usd_to_krw_rate
    car_data["svh_russia_rub"] = 50000

    car_data["lab_russia_usd"] = 30000 / usd_to_rub_rate
    car_data["lab_russia_krw"] = (30000 / usd_to_rub_rate) * usd_to_krw_rate
    car_data["lab_russia_rub"] = 30000

    car_data["perm_registration_russia_usd"] = 8000 / usd_to_rub_rate
    car_data["perm_registration_russia_krw"] = (
        8000 / usd_to_rub_rate
    ) * usd_to_krw_rate
    car_data["perm_registration_russia_rub"] = 8000

    car_data["russia_total_usd"] = (
        (customs_duty / usd_to_rub_rate)
        + (customs_fee / usd_to_rub_rate)
        + (recycling_fee / usd_to_rub_rate)
        + (346)
        + (50000 / usd_to_rub_rate)
        + (8000 / usd_to_rub_rate)
    )
    car_data["russia_total_krw"] = (
        ((customs_duty / usd_to_rub_rate) * usd_to_krw_rate)
        + ((customs_fee / usd_to_rub_rate) * usd_to_krw_rate)
        + ((recycling_fee / usd_to_rub_rate) * usd_to_krw_rate)
        + (346 * usd_to_krw_rate)
        + ((50000 / usd_to_rub_rate) * usd_to_krw_rate)
        + ((8000 / usd_to_rub_rate) * usd_to_krw_rate)
    )
    car_data["russia_total_rub"] = (
        customs_duty
        + customs_fee
        + recycling_fee
        + (346 * usd_to_rub_rate)
        + 50000
        + 8000
    )

    # Handle chutcha insurance payments
    car_insurance_payments_chutcha = ""
    if "web.chutcha.net" in link:
        own_car_insurance_payments = context.get("own_car_insurance_payments")
        other_car_insurance_payments = context.get("other_car_insurance_payments")
        own_insurance_text = (
            f"₩{format_number(own_car_insurance_payments)}"
            if isinstance(own_car_insurance_payments, int)
            else "Нет"
        )
        other_insurance_text = (
            f"₩{format_number(other_car_insurance_payments)}"
            if isinstance(other_car_insurance_payments, int)
            else "Нет"
        )

        car_insurance_payments_chutcha = (
            f"Страховые выплаты по данному автомобилю:\n{own_insurance_text}\n"
            f"Страховые выплаты другому автомобилю:\n{other_insurance_text}\n\n"
        )

    # Формирование сообщения результата
    result_message = (
        f"{car_title}\n\n"
        f"Возраст: {age_formatted} (дата регистрации: {month}/{year})\n"
        f"Пробег: {formatted_mileage}\n"
        f"Объём двигателя: {engine_volume_formatted}\n"
        f"Мощность: {hp} л.с.\n"
        f"КПП: {formatted_transmission}\n\n"
        f"Стоимость автомобиля в Корее: ₩{format_number(price_krw)}\n"
        f"Стоимость автомобиля под ключ до Владивостока: \n<b>${format_number(total_cost_usd)} </b> | <b>₩{format_number(total_cost_krw)} </b> | <b>{format_number(total_cost)} ₽</b>\n\n"
        f"{car_insurance_payments_chutcha}"
        f"💵 <b>Курс USDT к Воне: ₩{format_number(usdt_to_krw_rate)}</b>\n\n"
        f"🔗 <a href='{preview_link}'>Ссылка на автомобиль</a>\n\n"
        "Если данное авто попадает под санкции, пожалуйста уточните возможность отправки в вашу страну у наших менеджеров:\n\n"
        f"▪️ +82-10-8855-0386 (Андрей)\n"
        "🔗 <a href='https://t.me/dey_trading'>Официальный телеграм канал</a>\n"
    )

    # Клавиатура с дальнейшими действиями
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton("Детали расчёта", callback_data="detail")
    )

    # Кнопка для добавления в избранное
    keyboard.add(
        types.InlineKeyboardButton(
            "⭐ Добавить в избранное",
            callback_data=f"add_favorite_{car_id}",
        )
    )

    if "fem.encar.com" in link:
        keyboard.add(
            types.InlineKeyboardButton(
                "Технический Отчёт об Автомобиле", callback_data="technical_card"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Выплаты по ДТП",
                callback_data="technical_report",
            )
        )
    keyboard.add(
        types.InlineKeyboardButton(
            "Написать менеджеру", url="https://t.me/DeyTrading6"
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "Расчёт другого автомобиля",
            callback_data="calculate_another",
        )
    )
    keyboard.add(
        types.InlineKeyboardButton(
            "Главное меню",
            callback_data="main_menu",
        )
    )

    # Отправляем до 10 фотографий
    media_group = []
    for photo_url in sorted(car_photos):
        try:
            response = requests.get(photo_url)
            if response.status_code == 200:
                photo = BytesIO(response.content)
                media_group.append(types.InputMediaPhoto(photo))

                if len(media_group) == 10:
                    bot.send_media_group(user_id, media_group)
                    media_group.clear()
            else:
                print(f"Ошибка загрузки фото: {photo_url} - {response.status_code}")
        except Exception as e:
            print(f"Ошибка при обработке фото {photo_url}: {e}")

    # Отправка оставшихся фото, если их меньше 10
    if media_group:
        bot.send_media_group(user_id, media_group)

    car_data["car_id"] = car_id
    car_data["name"] = car_title
    car_data["images"] = car_photos if isinstance(car_photos, list) else []
    car_data["link"] = preview_link
    car_data["year"] = year
    car_data["month"] = month
    car_data["mileage"] = formatted_mileage
    car_data["engine_volume"] = car_engine_displacement
    car_data["transmission"] = formatted_transmission
    car_data["car_price"] = price_krw
    car_data["user_name"] = message.from_user.username
    car_data["first_name"] = message.from_user.first_name
    car_data["last_name"] = message.from_user.last_name

    bot.send_message(
        user_id,
        result_message,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    # Delete processing message if it exists
    if processing_message_id:
        try:
            bot.delete_message(user_id, processing_message_id)
        except Exception:
            pass


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_message = message.text.strip()

    # Добавляем пользователя в базу данных при каждом взаимодействии
    user_data = {
        "user_id": message.from_user.id,
        "username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "last_name": message.from_user.last_name,
        "phone_number": user_contacts.get(message.from_user.id, None),
    }
    add_or_update_user(user_data)

    # Проверяем нажатие кнопки "Рассчитать автомобиль"
    if user_message == CALCULATE_CAR_TEXT:
        bot.send_message(
            message.chat.id,
            "Пожалуйста, введите ссылку на автомобиль с одного из сайтов (encar.com, kbchachacha.com, web.chutcha.net):",
        )

    elif user_message == "Ручной расчёт":
        # Запрашиваем возраст автомобиля
        keyboard = types.ReplyKeyboardMarkup(
            resize_keyboard=True, one_time_keyboard=True
        )
        keyboard.add("До 3 лет", "От 3 до 5 лет")
        keyboard.add("От 5 до 7 лет", "Более 7 лет")

        bot.send_message(
            message.chat.id,
            "Выберите возраст автомобиля:",
            reply_markup=keyboard,
        )
        bot.register_next_step_handler(message, process_car_age)

    elif user_message == "Заказ запчастей":
        bot.send_message(
            message.chat.id,
            "Для оформления заявки на заказ запчастей пожалуйста напишите нашему менеджеру\n@KHAN_ALEX2022",
        )

    # Проверка на корректность ссылки
    elif re.match(
        r"^https?://(www|fem)\.encar\.com/.*|^https?://(www\.)?kbchachacha\.com/.*|^https?://m\.kbchachacha\.com/.*|^https?://(web\.)?chutcha\.net/.*",
        user_message,
    ):
        calculate_cost(user_message, message)

    # Проверка на другие команды
    elif user_message == "Написать менеджеру":
        managers_list = [
            {"name": "Андрей (Корея)", "whatsapp": "https://wa.me/821088550386"},
        ]

        # Формируем сообщение со списком менеджеров
        message_text = "Вы можете связаться с одним из наших менеджеров:\n\n"
        for manager in managers_list:
            message_text += f"[{manager['name']}]({manager['whatsapp']})\n"

        # Отправляем сообщение с использованием Markdown
        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")

    elif user_message == "Написать в WhatsApp":
        contacts = [
            {"name": "Константин", "phone": "+82 10-7650-3034"},
            {"name": "Владимир", "phone": "+82 10-7930-2218"},
            {"name": "Илья", "phone": "+82 10-3458-2205"},
        ]

        message_text = "\n".join(
            [
                f"[{contact['name']}](https://wa.me/{contact['phone'].replace('+', '')})"
                for contact in contacts
            ]
        )
        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")

    elif user_message == "О нас":
        about_message = "Dey Trading\nЮжнокорейская экспортная компания.\nСпециализируемся на поставках автомобилей из Южной Кореи в страны СНГ.\nОпыт работы более 5 лет.\n\nПочему выбирают нас?\n• Надежность и скорость доставки.\n• Индивидуальный подход к каждому клиенту.\n• Полное сопровождение сделки.\n\n💬 Ваш путь к надежным автомобилям начинается здесь!"
        bot.send_message(message.chat.id, about_message)

    elif user_message == "Telegram-канал":
        channel_link = "https://t.me/dey_trading"
        bot.send_message(
            message.chat.id, f"Подписывайтесь на наш Telegram-канал: {channel_link}"
        )
    elif user_message == "Instagram":
        instagram_link = "https://www.instagram.com/dey.trading"
        bot.send_message(
            message.chat.id,
            f"Посетите наш Instagram: {instagram_link}",
        )
    elif user_message == "Tik-Tok":
        tiktok_link = "https://www.tiktok.com/@dey.trading6"
        bot.send_message(
            message.chat.id,
            f"Следите за свежим контентом на нашем TikTok: {tiktok_link}",
        )

    elif user_message == "ВКонтакте":
        vk_link = "https://vk.com/id1028743915"
        bot.send_message(
            message.chat.id,
            f"Подписывайтесь на нас в ВКонтакте: {vk_link}",
        )

    elif user_message == "Facebook":
        facebook_link = "https://www.facebook.com/share/1D8bg2xL1i/?mibextid=wwXIfr"
        bot.send_message(
            message.chat.id,
            f"KPP Motors на Facebook: {facebook_link}",
        )
    else:
        bot.send_message(
            message.chat.id,
            "Пожалуйста, введите ссылку на автомобиль с сайта (encar.com, kbchachacha.com, web.chutcha.net)",
        )


# Run the bot
if __name__ == "__main__":
    create_tables()
    set_bot_commands()
    get_currency_rates()
    get_rub_to_krw_rate()
    get_usdt_to_krw_rate()

    # Обновляем курс каждые 12 часов
    scheduler = BackgroundScheduler()
    scheduler.add_job(get_usdt_to_krw_rate, "interval", hours=12)
    scheduler.start()

    bot.polling(non_stop=True)

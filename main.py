import telebot
import os
import re
import requests
import locale
import logging
import urllib.parse

from io import BytesIO
from telebot import types
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs
from utils import (
    generate_encar_photo_url,
    clean_number,
    get_customs_fees,
    calculate_age,
    format_number,
)

CALCULATE_CAR_TEXT = "Рассчитать Автомобиль по ссылке с Encar"

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

car_month = None
car_year = None

vehicle_id = None
vehicle_no = None


usd_to_krw_rate = 0
usd_to_rub_rate = 0


def print_message(message):
    print("\n\n##############")
    print(f"{message}")
    print("##############\n\n")
    return None


# Функция для установки команд меню
def set_bot_commands():
    commands = [
        types.BotCommand("start", "Запустить бота"),
        types.BotCommand("rates", "Курсы валют"),
    ]
    bot.set_my_commands(commands)


def get_rub_to_krw_rate():
    global rub_to_krw_rate

    url = "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/rub.json"

    try:
        response = requests.get(url)
        response.raise_for_status()  # Проверяем, что запрос успешный (код 200)
        data = response.json()

        rub_to_krw = data["rub"]["krw"]  # Достаем курс рубля к воне
        rub_to_krw_rate = rub_to_krw

    except requests.RequestException as e:
        print(f"Ошибка при получении курса: {e}")
        return None


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


# Пример вызова
rate = get_rub_to_krw_rate()
if rate:
    print(f"Текущий курс RUB → KRW: {rate:.2f} ₩")
else:
    print("Не удалось получить курс.")


# Функция для получения курсов валют с API
def get_usd_to_krw_rate():
    global usd_to_krw_rate

    url = "https://api.manana.kr/exchange/rate/KRW/USD.json"

    try:
        response = requests.get(url)
        response.raise_for_status()  # Проверяем успешность запроса
        data = response.json()

        # Получаем курс и добавляем +25 KRW
        usd_to_krw = data[0]["rate"] + 25
        usd_to_krw_rate = usd_to_krw

        print(f"Курс USD → KRW (с учетом +25 KRW): {usd_to_krw_rate}")
    except requests.RequestException as e:
        print(f"Ошибка при получении курса USD → KRW: {e}")
        usd_to_krw_rate = None


def get_usd_to_rub_rate():
    global usd_to_rub_rate

    url = "https://mosca.moscow/api/v1/rate/"
    headers = {
        "Access-Token": "JI_piVMlX9TsvIRKmduIbZOWzLo-v2zXozNfuxxXj4_MpsUKd_7aQS16fExzA7MVFCVVoAAmrb_-aMuu_UIbJA"
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Проверяем успешность запроса
        data = response.json()

        # Получаем курс USD → RUB
        usd_to_rub = data["buy"]
        usd_to_rub_rate = usd_to_rub

        print(f"Курс USD → RUB: {usd_to_rub_rate}")
    except requests.RequestException as e:
        print(f"Ошибка при получении курса USD → RUB: {e}")
        usd_to_rub_rate = None


# Обработчик команды /rates
@bot.message_handler(commands=["rates"])
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
        types.KeyboardButton("Заказ запчастей"),
    )
    keyboard.add(
        types.KeyboardButton("Написать менеджеру"),
        types.KeyboardButton("О нас"),
        types.KeyboardButton("Telegram-канал"),
        # types.KeyboardButton("Написать в WhatsApp"),
        types.KeyboardButton("Instagram"),
        types.KeyboardButton("Tik-Tok"),
        # types.KeyboardButton("Facebook"),
    )
    return keyboard


# Start command handler
@bot.message_handler(commands=["start"])
def send_welcome(message):
    get_currency_rates()

    user_first_name = message.from_user.first_name
    welcome_message = (
        f"Здравствуйте, {user_first_name}!\n\n"
        "Я бот компании DeyTrading. Я помогу вам рассчитать стоимость понравившегося вам автомобиля из Южной Кореи до стран СНГ.\n\n"
        "Выберите действие из меню ниже."
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

    # driver = create_driver()

    car_id_match = re.findall(r"\d+", url)
    car_id = car_id_match[0]
    car_id_external = car_id

    url = f"https://api.encar.com/v1/readside/vehicle/{car_id}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "http://www.encar.com/",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
    }

    response = requests.get(url, headers=headers).json()

    # Информация об автомобиле
    car_make = response["category"]["manufacturerEnglishName"]  # Марка
    car_model = response["category"]["modelGroupEnglishName"]  # Модель
    car_trim = response["category"]["gradeDetailEnglishName"] or ""  # Комплектация

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


# Function to calculate the total cost
def calculate_cost(link, message):
    global car_data, car_id_external, car_month, car_year, krw_rub_rate, eur_rub_rate, rub_to_krw_rate, usd_rate

    print_message("ЗАПРОС НА РАСЧЁТ АВТОМОБИЛЯ")

    # Отправляем сообщение и сохраняем его ID
    processing_message = bot.send_message(
        message.chat.id, "Обрабатываю данные. Пожалуйста подождите ⏳"
    )

    car_id = None

    # Проверка ссылки на мобильную версию
    if "fem.encar.com" in link:
        car_id_match = re.findall(r"\d+", link)
        if car_id_match:
            car_id = car_id_match[0]  # Use the first match of digits
            car_id_external = car_id
            link = f"https://fem.encar.com/cars/detail/{car_id}"
        else:
            send_error_message(message, "🚫 Не удалось извлечь carid из ссылки.")
            return
    else:
        # Извлекаем carid с URL encar
        parsed_url = urlparse(link)
        query_params = parse_qs(parsed_url.query)
        car_id = query_params.get("carid", [None])[0]

    result = get_car_info(link)
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

    if not car_price and car_engine_displacement and formatted_car_date:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "Написать менеджеру", url="https://t.me/@timyo97"
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

    # Если есть новая ссылка
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

        response = get_customs_fees(
            car_engine_displacement,
            price_krw,
            int(f"20{car_year}"),
            car_month,
            engine_type=1,
        )

        # Таможенный сбор
        customs_fee = clean_number(response["sbor"])
        customs_duty = clean_number(response["tax"])
        recycling_fee = clean_number(response["util"])

        # Расчет итоговой стоимости автомобиля в рублях
        total_cost = (
            50000
            + (price_rub)
            + ((440000 / usd_to_krw_rate) * usd_to_rub_rate)
            + ((100000 / usd_to_krw_rate) * usd_to_rub_rate)
            + ((350000 / usd_to_krw_rate) * usd_to_rub_rate)
            + (600 * usd_to_rub_rate)
            + customs_duty
            + customs_fee
            + recycling_fee
            + (346 * usd_to_rub_rate)
            + 50000
            + 30000
            + 8000
        )

        total_cost_krw = (
            ((50000 / usd_to_rub_rate) * usd_to_krw_rate)
            + (price_krw)
            + 440000
            + 100000
            + 350000
            + ((600 * usd_to_krw_rate))
            + ((customs_duty / usd_to_rub_rate) * usd_to_krw_rate)
            + ((customs_fee / usd_to_rub_rate) * usd_to_krw_rate)
            + ((recycling_fee / usd_to_rub_rate) * usd_to_krw_rate)
            + (346 * usd_to_krw_rate)
            + ((50000 / usd_to_rub_rate) * usd_to_krw_rate)
            + ((30000 / usd_to_rub_rate) * usd_to_krw_rate)
            + ((8000 / usd_to_rub_rate) * usd_to_krw_rate)
        )

        total_cost_usd = (
            (50000 / usd_to_rub_rate)
            + (price_usd)
            + (440000 / usd_to_krw_rate)
            + (100000 / usd_to_krw_rate)
            + (350000 / usd_to_krw_rate)
            + (600)
            + (customs_duty / usd_to_rub_rate)
            + (customs_fee / usd_to_rub_rate)
            + (recycling_fee / usd_to_rub_rate)
            + (346)
            + (50000 / usd_to_rub_rate)
            + (30000 / usd_to_rub_rate)
            + (8000 / usd_to_rub_rate)
        )

        car_data["total_cost_usd"] = total_cost_usd
        car_data["total_cost_krw"] = total_cost_krw
        car_data["total_cost_rub"] = total_cost

        car_data["agent_korea_rub"] = 50000
        car_data["agent_korea_usd"] = 50000 / usd_to_rub_rate
        car_data["agent_korea_krw"] = (50000 / usd_to_rub_rate) * usd_to_krw_rate

        car_data["advance_rub"] = (1000000 / usd_to_krw_rate) * usd_to_rub_rate
        car_data["advance_usd"] = 1000000 * usd_to_krw_rate
        car_data["advance_krw"] = 1000000

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

        car_data["freight_korea_usd"] = 600
        car_data["freight_korea_krw"] = 600 * usd_to_krw_rate
        car_data["freight_korea_rub"] = 600 * usd_to_rub_rate

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

        car_data["broker_russia_usd"] = 346
        car_data["broker_russia_krw"] = 346 * usd_to_krw_rate
        car_data["broker_russia_rub"] = 346 * usd_to_rub_rate

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

        preview_link = f"https://fem.encar.com/cars/detail/{car_id}"

        # Формирование сообщения результата
        result_message = (
            f"{car_title}\n\n"
            f"Возраст: {age_formatted} (дата регистрации: {month}/{year})\n"
            f"Пробег: {formatted_mileage}\n"
            f"Объём двигателя: {engine_volume_formatted}\n"
            f"КПП: {formatted_transmission}\n\n"
            f"Стоимость автомобиля в Корее: ₩{format_number(price_krw)}\n"
            f"Стоимость автомобиля под ключ до Владивостока: \n<b>${format_number(total_cost_usd)} </b> | <b>₩{format_number(total_cost_krw)} </b> | <b>{format_number(total_cost)} ₽</b>\n\n"
            f"🔗 <a href='{preview_link}'>Ссылка на автомобиль</a>\n\n"
            "Если данное авто попадает под санкции, пожалуйста уточните возможность отправки в вашу страну у наших менеджеров:\n\n"
            f"▪️ +82 10-2934-8855 (Артур)\n"
            f"▪️ +82 10-5528-0997 (Тимур)\n"
            f"▪️ +82 10-5128-8082 (Александр) \n\n"
            "🔗 <a href='https://t.me/akmotors96'>Официальный телеграм канал</a>\n"
        )

        # Клавиатура с дальнейшими действиями
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("Детали расчёта", callback_data="detail")
        )
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
                "Написать менеджеру", url="https://t.me/@timyo97"
            )
        )
        keyboard.add(
            types.InlineKeyboardButton(
                "Расчёт другого автомобиля",
                callback_data="calculate_another",
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

        response = requests.get(url, headers)
        json_response = response.json()

        # Форматируем данные
        damage_to_my_car = json_response["myAccidentCost"]
        damage_to_other_car = json_response["otherAccidentCost"]

        print(
            f"Выплаты по представленному автомобилю: {format_number(damage_to_my_car)}"
        )
        print(f"Выплаты другому автомобилю: {format_number(damage_to_other_car)}")

        return [format_number(damage_to_my_car), format_number(damage_to_other_car)]

    except Exception as e:
        print(f"Произошла ошибка при получении данных: {e}")
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

        response = requests.get(url, headers)
        json_response = response.json()

        # Основная информация
        model_year = (
            json_response.get("master", {}).get("detail", {}).get("modelYear", "")
        )
        first_registration_date = (
            json_response.get("master", {})
            .get("detail", {})
            .get("firstRegistrationDate", "")
        )
        comments = (
            json_response.get("master", {})
            .get("detail", {})
            .get("comments", "")
            .strip()
        )
        usage_change_types = (
            json_response.get("master", {})
            .get("detail", {})
            .get("usageChangeTypes", [])
        )
        paint_part_types = (
            json_response.get("master", {}).get("detail", {}).get("paintPartTypes", [])
        )
        serious_types = (
            json_response.get("master", {}).get("detail", {}).get("seriousTypes", [])
        )
        tuning_state_types = (
            json_response.get("master", {})
            .get("detail", {})
            .get("tuningStateTypes", [])
        )
        etcs = json_response.get("etcs", [])

        # Перевод использования
        usage_translation = {
            "렌트": "Аренда",
            "리스": "Лизинг",
            "영업용": "Коммерческое использование",
        }
        usage_change = "Не указано"
        if usage_change_types:
            usage_change = usage_translation.get(
                usage_change_types[0].get("title", ""), "Не указано"
            )

        # Перевод комментариев
        if not comments:
            comments = "Нет данных"
        else:
            comments = comments.replace(
                "조 앞/뒤 도어 판금도색", "Передняя/задняя дверь: Рихтовка и покраска"
            )

        # Необходимость ремонта
        repair_needed = []
        for etc in etcs:
            title = etc["type"]["title"]
            if title == "수리필요":
                for child in etc["children"]:
                    repair_needed.append(child["type"]["title"])

        repair_translation = {
            "외장": "Кузов",
            "내장": "Интерьер",
            "광택": "Полировка",
            "룸 클리링": "Чистка салона",
            "휠": "Колёса",
            "타이어": "Шины",
            "유리": "Стекло",
        }
        repair_needed_translated = [
            repair_translation.get(item, item) for item in repair_needed
        ]
        repair_output = (
            "Нет данных"
            if not repair_needed_translated
            else "\n".join(
                [f"- {item}: Требуется ремонт" for item in repair_needed_translated]
            )
        )

        # Окрашенные элементы
        painted_parts = (
            "Нет данных" if not paint_part_types else "\n".join(paint_part_types)
        )

        # Серьёзные повреждения
        serious_damages = (
            "Нет данных" if not serious_types else "\n".join(serious_types)
        )

        # Тюнинг и модификации
        tuning_mods = (
            "Нет данных" if not tuning_state_types else "\n".join(tuning_state_types)
        )

        # Сборка сообщения
        output = (
            f"🚗 <b>Технический отчёт об автомобиле</b> 🚗\n\n"
            # f"📅 <b>Дата первой регистрации</b>: {first_registration_date}\n"
            f"🛠 <b>Обновление тех. состояния</b>: {model_year}\n\n"
            f"🔧 <b>Использование автомобиля</b>: {usage_change}\n\n"
            # f"📋 <b>Комментарии</b>:\n{comments}\n\n"
            f"⚙️ <b>Необходимость ремонта</b>:\n{repair_output}\n\n"
            f"🎨 <b>Окрашенные элементы</b>:\n{painted_parts}\n\n"
            f"🚧 <b>Серьёзные повреждения</b>:\n{serious_damages}\n\n"
            f"🔧 <b>Тюнинг и модификации</b>:\n{tuning_mods}"
        )

        return output

    except Exception as e:
        print(f"Произошла ошибка при получении данных: {e}")
        return "Произошла ошибка при получении данных"


# Callback query handler
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    global car_data, car_id_external, usd_rate

    if call.data.startswith("detail"):
        print_message("[ЗАПРОС] ДЕТАЛИЗАЦИЯ РАСЧËТА")

        detail_message = (
            f"<i>ПЕРВАЯ ЧАСТЬ ОПЛАТЫ</i>:\n\n"
            f"Агентские услуги по договору:\n<b>${format_number(car_data['agent_korea_usd'])}</b> | <b>₩{format_number(car_data['agent_korea_krw'])}</b> | <b>50000 ₽</b>\n\n"
            f"Задаток (бронь авто):\n<b>${format_number(car_data['advance_usd'])}</b> | <b>₩1,000,000</b> | <b>{format_number(car_data['advance_rub'])} ₽</b>\n\n\n"
            f"<i>ВТОРАЯ ЧАСТЬ ОПЛАТЫ</i>:\n\n"
            # f"Стоимость автомобиля (за вычетом задатка):\n<b>${format_number(car_data['car_price_usd'])}</b> | <b>₩{format_number(car_data['car_price_krw'])}</b> | <b>{format_number(car_data['car_price_rub'])} ₽</b>\n\n"
            f"Диллерский сбор:\n<b>${format_number(car_data['dealer_korea_usd'])}</b> | <b>₩{format_number(car_data['dealer_korea_krw'])}</b> | <b>{format_number(car_data['dealer_korea_rub'])} ₽</b>\n\n"
            f"Доставка, снятие с учёта, оформление:\n<b>${format_number(car_data['delivery_korea_usd'])}</b> | <b>₩{format_number(car_data['delivery_korea_krw'])}</b> | <b>{format_number(car_data['delivery_korea_rub'])} ₽</b>\n\n"
            f"Транспортировка авто в порт:\n<b>${format_number(car_data['transfer_korea_usd'])}</b> | <b>₩{format_number(car_data['transfer_korea_krw'])}</b> | <b>{format_number(car_data['transfer_korea_rub'])} ₽</b>\n\n"
            f"Фрахт (Паром до Владивостока):\n<b>${format_number(car_data['freight_korea_usd'])}</b> | <b>₩{format_number(car_data['freight_korea_krw'])}</b> | <b>{format_number(car_data['freight_korea_rub'])} ₽</b>\n\n\n"
            f"<b>Итого расходов по Корее</b>:\n<b>${format_number(car_data['korea_total_usd'])}</b> | <b>₩{format_number(car_data['korea_total_krw'])}</b> | <b>{format_number(car_data['korea_total_rub'])} ₽</b>\n\n"
            f"<b>Стоимость автомобиля</b>:\n<b>${format_number(car_data['car_price_usd'])}</b> | <b>₩{format_number(car_data['car_price_krw'])}</b> | <b>{format_number(car_data['car_price_rub'])} ₽</b>\n\n"
            f"<b>Итого</b>:\n<b>${format_number(car_data['korea_total_plus_car_usd'])}</b> | <b>₩{format_number(car_data['korea_total_plus_car_krw'])}</b> | <b>{format_number(car_data['korea_total_plus_car_rub'])} ₽</b>\n\n\n"
            f"<i>РАСХОДЫ РОССИЯ</i>:\n\n\n"
            f"Единая таможенная ставка:\n<b>${format_number(car_data['customs_duty_usd'])}</b> | <b>₩{format_number(car_data['customs_duty_krw'])}</b> | <b>{format_number(car_data['customs_duty_rub'])} ₽</b>\n\n"
            f"Таможенное оформление:\n<b>${format_number(car_data['customs_fee_usd'])}</b> | <b>₩{format_number(car_data['customs_fee_krw'])}</b> | <b>{format_number(car_data['customs_fee_rub'])} ₽</b>\n\n"
            f"Утилизационный сбор:\n<b>${format_number(car_data['util_fee_usd'])}</b> | <b>₩{format_number(car_data['util_fee_krw'])}</b> | <b>{format_number(car_data['util_fee_rub'])} ₽</b>\n\n\n"
            f"Брокер-Владивосток:\n<b>${format_number(car_data['broker_russia_usd'])}</b> | <b>₩{format_number(car_data['broker_russia_krw'])}</b> | <b>{format_number(car_data['broker_russia_rub'])} ₽</b>\n\n"
            f"СВХ-Владивосток:\n<b>${format_number(car_data['svh_russia_usd'])}</b> | <b>₩{format_number(car_data['svh_russia_krw'])}</b> | <b>{format_number(car_data['svh_russia_rub'])} ₽</b>\n\n"
            f"Лаборатория, СБКТС, ЭПТС:\n<b>${format_number(car_data['lab_russia_usd'])}</b> | <b>₩{format_number(car_data['lab_russia_krw'])}</b> | <b>{format_number(car_data['lab_russia_rub'])} ₽</b>\n\n"
            f"Временная регистрация-Владивосток:\n<b>${format_number(car_data['perm_registration_russia_usd'])}</b> | <b>₩{format_number(car_data['perm_registration_russia_krw'])}</b> | <b>{format_number(car_data['perm_registration_russia_rub'])} ₽</b>\n\n"
            f"Итого расходов по России: \n<b>${format_number(car_data['russia_total_usd'])}</b> | <b>₩{format_number(car_data['russia_total_krw'])}</b> | <b>{format_number(car_data['russia_total_rub'])} ₽</b>\n\n\n"
            f"Итого под ключ во Владивостоке: \n<b>${format_number(car_data['total_cost_usd'])}</b> | <b>₩{format_number(car_data['total_cost_krw'])}</b> | <b>{format_number(car_data['total_cost_rub'])} ₽</b>\n\n"
            f"<b>Доставку до вашего города уточняйте у менеджеров:</b>\n"
            f"▪️ +82 10-2934-8855 (Артур)\n"
            f"▪️ +82 10-5528-0997 (Тимур)\n"
            f"▪️ +82 10-5128-8082 (Александр)\n\n"
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

        # keyboard.add(
        #     types.InlineKeyboardButton(
        #         "Связаться с менеджером", url="https://t.me/@timyo97"
        #     )
        # )

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
        # keyboard.add(
        #     types.InlineKeyboardButton(
        #         "Связаться с менеджером", url="https://t.me/@timyo97"
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
                    "Связаться с менеджером", url="https://t.me/@timyo97"
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
                    "Связаться с менеджером", url="https://t.me/@timyo97"
                )
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
            "Пожалуйста, введите ссылку на автомобиль с сайта www.encar.com:",
        )


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_message = message.text.strip()

    # Проверяем нажатие кнопки "Рассчитать автомобиль"
    if user_message == CALCULATE_CAR_TEXT:
        bot.send_message(
            message.chat.id,
            "Пожалуйста, введите ссылку на автомобиль с сайта www.encar.com:",
        )

    elif user_message == "Заказ запчастей":
        bot.send_message(
            message.chat.id,
            "Для оформления заявки на заказ запчастей пожалуйста напишите нашему менеджеру\n@KHAN_ALEX2022",
        )

    # Проверка на корректность ссылки
    elif re.match(r"^https?://(www|fem)\.encar\.com/.*", user_message):
        calculate_cost(user_message, message)

    # Проверка на другие команды
    elif user_message == "Написать менеджеру":
        managers_list = [
            {"name": "Ким Артур (Корея)", "whatsapp": "https://wa.me/821029348855"},
            {"name": "Ким Артур (Россия)", "whatsapp": "https://wa.me/79999000070"},
            {"name": "Тимур", "whatsapp": "https://wa.me/821055280997"},
            {"name": "Александр", "whatsapp": "https://wa.me/821051288082"},
        ]

        # Формируем сообщение со списком менеджеров
        message_text = "Вы можете связаться с одним из наших менеджеров:\n\n"
        for manager in managers_list:
            message_text += f"[{manager['name']}]({manager['whatsapp']})\n"

        # Отправляем сообщение с использованием Markdown
        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")

    elif user_message == "Написать в WhatsApp":
        contacts = [
            {
                "name": "Андрей",
                "phone": "+82 10-8855-0386",
                "whatsapp_phone": "821088550386",
            },
            # {"name": "Владимир", "phone": "+82 10-7930-2218"},
            # {"name": "Илья", "phone": "+82 10-3458-2205"},
        ]

        message_text = "\n".join(
            [
                f"[{contact['name']}](https://wa.me/{contact['whatsapp_phone'].replace('+', '')})"
                for contact in contacts
            ]
        )
        bot.send_message(message.chat.id, message_text, parse_mode="Markdown")

    elif user_message == "О нас":
        about_message = "DeyTrading \nЮжнокорейская экспортная компания.\nСпециализируемся на поставках автомобилей из Южной Кореи в страны СНГ.\nОпыт работы более 5 лет.\n\nПочему выбирают нас?\n• Надежность и скорость доставки.\n• Индивидуальный подход к каждому клиенту.\n• Полное сопровождение сделки.\n\n💬 Ваш путь к надежным автомобилям начинается здесь!"
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
    elif user_message == "Facebook":
        facebook_link = "https://www.facebook.com/share/1D8bg2xL1i/?mibextid=wwXIfr"
        bot.send_message(
            message.chat.id,
            f"KPP Motors на Facebook: {facebook_link}",
        )
    else:
        bot.send_message(
            message.chat.id,
            "Пожалуйста, введите корректную ссылку на автомобиль с сайта www.encar.com или fem.encar.com.",
        )


# Run the bot
if __name__ == "__main__":
    # initialize_db()
    set_bot_commands()
    get_rub_to_krw_rate()
    get_currency_rates()
    bot.polling(non_stop=True)

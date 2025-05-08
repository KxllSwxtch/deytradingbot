import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")  # Берём из переменных окружения


def connect_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def create_tables():
    """Создаём таблицу заказов, если её нет."""
    with connect_db() as conn:
        with conn.cursor() as cur:
            # Таблица пользователей
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    phone_number TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    car_id TEXT NOT NULL,  -- ✅ Добавили car_id
                    title TEXT NOT NULL,
                    price TEXT,
                    link TEXT NOT NULL,
                    year TEXT,
                    month TEXT,
                    mileage TEXT,
                    engine_volume INT,
                    transmission TEXT,
                    user_name TEXT,
                    full_name TEXT,
                    phone_number TEXT,
                    images TEXT[],
                    status TEXT DEFAULT '🔄 Не заказано',
                    total_cost_usd FLOAT,
                    total_cost_krw FLOAT,
                    total_cost_rub FLOAT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """
            )

            # Добавляем поле created_at для существующей таблицы, если его еще нет
            cur.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 
                        FROM information_schema.columns 
                        WHERE table_name='orders' AND column_name='created_at'
                    ) THEN
                        ALTER TABLE orders ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                    END IF;
                END$$;
                """
            )

            # ✅ Добавляем таблицу расчётов
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS calculations (
                    user_id BIGINT PRIMARY KEY,
                    count INT DEFAULT 0
                );
            """
            )

            # ✅ Таблица подписок
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    user_id BIGINT PRIMARY KEY,
                    status BOOLEAN DEFAULT FALSE
                );
                """
            )

            conn.commit()


def add_order(order):
    """Добавляем заказ в базу данных."""
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orders (user_id, car_id, title, price, link, year, month, mileage, engine_volume, 
                                    transmission, user_name, phone_number, images, status, total_cost_usd, total_cost_krw, total_cost_rub)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """,
                (
                    order["user_id"],
                    order["car_id"],
                    order["title"],
                    order["price"],
                    order["link"],
                    order["year"],
                    order["month"],
                    order["mileage"],
                    order["engine_volume"],
                    order["transmission"],
                    order["user_name"],
                    order["phone_number"],
                    order["images"],
                    order["status"],
                    order["total_cost_usd"],
                    order["total_cost_krw"],
                    order["total_cost_rub"],
                ),
            )
            conn.commit()


def get_orders(user_id):
    """Получает список заказов пользователя из базы данных"""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, car_id, title, status, link, year, month, mileage, engine_volume, transmission,
               total_cost_usd, total_cost_krw, total_cost_rub, user_name, full_name
        FROM orders
        WHERE user_id = %s
    """,
        (user_id,),
    )

    orders = cur.fetchall()
    cur.close()
    conn.close()

    # Преобразуем в список словарей
    return [
        {
            "id": order[1],  # ✅ car_id теперь вместо id
            "car_id": order[1],
            "title": order[2],
            "status": order[3],
            "link": order[4],
            "year": order[5],
            "month": order[6],
            "mileage": order[7],
            "engine_volume": order[8],
            "transmission": order[9],
            "total_cost_usd": order[10],
            "total_cost_krw": order[11],
            "total_cost_rub": order[12],
            "user_name": order[13],
            "full_name": order[14],  # ✅ ФИО клиента теперь загружается
        }
        for order in orders
    ]


def get_all_orders():
    """Получает список всех заказов для менеджеров"""
    with connect_db() as conn:
        with conn.cursor(
            cursor_factory=RealDictCursor
        ) as cur:  # ✅ Добавили `RealDictCursor`
            cur.execute(
                """
                SELECT id, car_id, user_id, user_name, phone_number, title, status, link, 
                       year, month, mileage, engine_volume, transmission, 
                       total_cost_usd, total_cost_krw, total_cost_rub, full_name
                FROM orders
            """
            )
            orders = cur.fetchall()

    return orders  # Теперь `orders` — список словарей, а не кортежей!


def update_order_status_in_db(order_id, new_status):
    """Обновляет статус заказа в базе данных"""
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET status = %s WHERE id = %s;",  # ❗ Используем `id`
                (new_status, order_id),
            )
            conn.commit()


def update_user_phone(user_id, phone_number, car_id):
    """Обновляет номер телефона в конкретном заказе пользователя."""
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET phone_number = %s WHERE user_id = %s AND car_id = %s;",  # ✅ Обновляем только один заказ
                (phone_number, user_id, str(car_id)),
            )
            conn.commit()


def delete_order_from_db(order_id):
    """Удаляет заказ из базы данных по order_id"""
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM orders WHERE id = %s;", (order_id,))
            conn.commit()
    print(f"✅ Заказ {order_id} удалён из базы!")


def update_user_name(user_id, full_name):
    """Обновляет ФИО пользователя в базе данных."""
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE orders SET user_name = %s WHERE user_id = %s;",
                (full_name, user_id),
            )
            conn.commit()


def get_calculation_count(user_id):
    """Получает количество расчётов пользователя."""
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count FROM calculations WHERE user_id = %s;", (user_id,)
            )
            result = cur.fetchone()
            return result["count"] if result else 0


def increment_calculation_count(user_id):
    """Увеличивает количество расчётов пользователя."""
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO calculations (user_id, count)
                VALUES (%s, 1)
                ON CONFLICT (user_id) DO UPDATE 
                SET count = calculations.count + 1;
                """,
                (user_id,),
            )
            conn.commit()


def reset_calculation_count(user_id):
    """Сбрасывает количество расчётов (например, после подписки)."""
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE calculations SET count = 0 WHERE user_id = %s;", (user_id,)
            )
            conn.commit()


def update_user_subscription(user_id, status):
    """Обновляет статус подписки пользователя."""
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO subscriptions (user_id, status)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE 
                SET status = EXCLUDED.status;
                """,
                (user_id, status),
            )
            conn.commit()


def check_user_subscription(user_id):
    """Проверяет, есть ли у пользователя активная подписка."""
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status FROM subscriptions WHERE user_id = %s;", (user_id,)
            )
            result = cur.fetchone()
            return result["status"] if result else False


def get_all_users():
    """Получает список всех уникальных пользователей бота из базы данных"""
    with connect_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (user_id) user_id, user_name, phone_number, 
                       (SELECT count FROM calculations WHERE calculations.user_id = orders.user_id) as calc_count,
                       (SELECT status FROM subscriptions WHERE subscriptions.user_id = orders.user_id) as subscription,
                       (SELECT created_at FROM orders o WHERE o.user_id = orders.user_id ORDER BY id ASC LIMIT 1) as first_activity
                FROM orders
                ORDER BY user_id, id ASC
                """
            )
            users = cur.fetchall()
    return users


def user_exists(user_id):
    """Проверяет, существует ли пользователь в базе данных"""
    with connect_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
            return cur.fetchone() is not None


def add_or_update_user(user_data):
    """Добавляет нового пользователя или обновляет существующего"""
    with connect_db() as conn:
        with conn.cursor() as cur:
            # Проверяем, есть ли уже пользователь с таким user_id
            cur.execute(
                """
                INSERT INTO users (user_id, username, first_name, last_name, phone_number)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    last_activity = CURRENT_TIMESTAMP
                """,
                (
                    user_data["user_id"],
                    user_data.get("username", None),
                    user_data.get("first_name", None),
                    user_data.get("last_name", None),
                    user_data.get("phone_number", None),
                ),
            )
            conn.commit()


def get_all_bot_users():
    """Получает список всех пользователей бота из таблицы users"""
    with connect_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT user_id, username, first_name, last_name, phone_number, created_at, last_activity,
                       (SELECT count FROM calculations WHERE calculations.user_id = users.user_id) as calc_count,
                       (SELECT status FROM subscriptions WHERE subscriptions.user_id = users.user_id) as subscription
                FROM users
                ORDER BY created_at DESC
                """
            )
            users = cur.fetchall()
    return users

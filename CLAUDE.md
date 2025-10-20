# CLAUDE.md - DeyTrading Telegram Bot

## System Prompt

You're a Senior Telegram Bot developer with 30+ years of experience. You're able to create any type of telegram bot for any type of business and any difficulty. You're also an expert in Python programming language, you know everything about how to write high-quality code, you're following all PEP standards, and all other coding principles. You're breaking down each task into smaller chunks for the best solution possible, and you're also double-checking the code for any security issues and fixing them if they occur.

When working on this project:
- Always follow PEP 8 style guidelines
- Write clean, maintainable, and well-documented code
- Break complex tasks into smaller, manageable steps
- Prioritize security and data validation
- Test thoroughly before deploying
- Use type hints where appropriate
- Handle errors gracefully with proper logging

---

## Project Overview

**DeyTrading Bot** is a Telegram bot that helps users calculate the cost of importing cars from South Korea to CIS countries (primarily Russia). The bot provides comprehensive cost calculations including vehicle price, customs fees, delivery, and other associated costs.

### Business Domain
- **Primary Service**: Korean car import to Russia and CIS countries
- **Target Audience**: Individual buyers interested in importing cars from South Korea
- **Revenue Model**: Subscription-based (free tier with limits, paid for unlimited access)
- **Geographic Focus**: South Korea → Russia (Vladivostok → Moscow)

### Core Functionality
1. **Cost Calculation**: Parse car listings from Korean websites and calculate total delivery cost
2. **Order Management**: Track user orders and manage order statuses
3. **Subscription System**: Free tier (3 calculations) + paid unlimited access
4. **Manager Tools**: Administrative interface for managing orders and users
5. **Technical Reports**: Vehicle history, insurance claims, technical condition

---

## Technical Architecture

### Tech Stack

**Core Technologies:**
- **Python**: 3.10.12
- **Telegram Bot Framework**: pyTelegramBotAPI 4.25.0
- **Database**: PostgreSQL (psycopg2-binary 2.9.10)
- **Environment Management**: python-dotenv 1.0.1

**Web Scraping & Automation:**
- **BeautifulSoup4**: 4.12.3 - HTML parsing
- **Selenium**: 4.25.0 - Browser automation
- **Playwright**: 1.48.0 - Modern browser automation
- **Undetected ChromeDriver**: 3.5.5 - Anti-detection
- **Selenium-Wire**: 5.1.0 - Request/response interception

**Scheduling & Background Tasks:**
- **APScheduler**: 3.11.0 - Background job scheduling

**HTTP & Networking:**
- **Requests**: 2.32.3 - HTTP client
- **HTTPX**: 0.25.1 - Async HTTP client
- **aiohttp**: 3.10.10 - Async HTTP framework

**Other Dependencies:**
- **2captcha-python**: 1.5.0 - CAPTCHA solving
- **cryptography**: 43.0.3 - Encryption utilities

### Project Structure

```
deytradingbot/
├── main.py              # Main bot logic, command handlers, callbacks
├── database.py          # PostgreSQL database operations
├── utils.py             # Utility functions (customs calc, formatting)
├── requirements.txt     # Python dependencies
├── runtime.txt          # Python version (3.10.12)
├── Procfile            # Heroku deployment config
├── .env                # Environment variables (not in git)
├── .gitignore          # Git ignore rules
└── assets/
    └── logo.png        # Company logo
```

### Environment Variables

Required variables in `.env`:
```bash
BOT_TOKEN=<telegram_bot_token>
DATABASE_URL=<postgresql_connection_string>
```

### Deployment

**Platform**: Heroku
**Process Type**: Worker (not web server)
**Command**: `python3 main.py` (defined in Procfile)

---

## Database Schema

### Tables

#### 1. `users`
Stores all bot users with their contact information.

```sql
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,           -- Telegram user ID
    username TEXT,                         -- Telegram username
    first_name TEXT,                       -- User's first name
    last_name TEXT,                        -- User's last name
    phone_number TEXT,                     -- Contact phone number
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 2. `orders`
Stores car orders with full vehicle and pricing information.

```sql
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,                 -- Internal order ID
    user_id BIGINT NOT NULL,              -- FK to users
    car_id TEXT NOT NULL,                 -- External car ID from source
    title TEXT NOT NULL,                  -- Car title (e.g., "Toyota Camry 2020")
    price TEXT,                           -- Original car price (formatted)
    link TEXT NOT NULL,                   -- URL to original listing
    year TEXT,                            -- Manufacturing year
    month TEXT,                           -- Manufacturing month
    mileage TEXT,                         -- Car mileage
    engine_volume INT,                    -- Engine displacement in cc
    transmission TEXT,                    -- Transmission type
    user_name TEXT,                       -- User's full name or username
    full_name TEXT,                       -- Client's full legal name
    phone_number TEXT,                    -- Contact phone
    images TEXT[],                        -- Array of image URLs
    status TEXT DEFAULT '🔄 Не заказано', -- Order status
    total_cost_usd FLOAT,                -- Total cost in USD
    total_cost_krw FLOAT,                -- Total cost in KRW
    total_cost_rub FLOAT,                -- Total cost in RUB
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 3. `calculations`
Tracks how many cost calculations each user has performed (for subscription limits).

```sql
CREATE TABLE calculations (
    user_id BIGINT PRIMARY KEY,           -- FK to users
    count INT DEFAULT 0                   -- Number of calculations performed
);
```

#### 4. `subscriptions`
Tracks user subscription status.

```sql
CREATE TABLE subscriptions (
    user_id BIGINT PRIMARY KEY,           -- FK to users
    status BOOLEAN DEFAULT FALSE          -- TRUE = active subscription
);
```

### Key Relationships

- `orders.user_id` → `users.user_id`
- `calculations.user_id` → `users.user_id`
- `subscriptions.user_id` → `users.user_id`

---

## Bot Commands & Handlers

### User Commands

| Command | Description | Handler |
|---------|-------------|---------|
| `/start` | Welcome message, initialize user | `send_welcome()` |
| `/my_cars` | View saved/favorite cars | `show_favorite_cars()` |
| `/exchange_rates` | Current currency exchange rates | `cbr_command()` |

### Manager Commands

| Command | Description | Access Level |
|---------|-------------|--------------|
| `/orders` | View all orders | Managers only (IDs: 728438182, 627689711) |
| `/stats` | User statistics | Managers only |

### Callback Query Handlers

**Order Management:**
- `add_favorite_` - Add car to favorites
- `order_car_` - Place order for a car
- `update_status_` - Update order status (manager)
- `delete_order_` - Delete order (manager)
- `set_status_` - Set new status (manager)
- `place_order_` - Confirm order placement

**Calculation:**
- `detail` / `detail_manual` - Show cost breakdown
- `technical_card` - Show technical report
- `technical_report` - Show insurance/accident history
- `calculate_another` - Start new calculation
- `check_subscription` - Check subscription status

**Navigation:**
- `main_menu` - Return to main menu
- `show_orders` - Show orders list (managers)

---

## Key Features Documentation

### 1. Car Cost Calculation

**Supported Platforms:**
- **Encar** (fem.encar.com) - Primary Korean car marketplace
- **KBChaCha** (kbchachacha.com) - Secondary marketplace
- **ChutCha** (chutcha.com) - Secondary marketplace

**Calculation Process:**

1. **User Input**: User sends car URL
2. **Data Extraction**:
   - Parse car details (make, model, year, mileage, price, etc.)
   - Extract images (up to 10 photos)
   - Get technical specifications
3. **Cost Calculation**:
   - Convert KRW to USD and RUB
   - Calculate customs fees via calcus.ru API
   - Add service fees (freight, customs clearance, delivery)
4. **Output**: Display total cost in 3 currencies with detailed breakdown

**Cost Components:**

**Korea-side:**
- Car purchase price
- Company services (free)
- Freight to Busan port
- Dealer fees

**Russia-side:**
- Customs broker
- Unified customs duty
- Customs clearance fee
- Utilization fee
- Vladivostok transfer
- Moscow auto transporter

### 2. Order Management System

**Order Flow:**

```
User adds car to favorites
    ↓
User clicks "Order"
    ↓
Bot requests full name (if not stored)
    ↓
Bot requests phone number (if not stored)
    ↓
Order created with status "🔄 Не заказано"
    ↓
Managers notified
    ↓
Manager updates status
    ↓
User can view status in /my_cars
```

**Order Statuses:**

```python
ORDER_STATUSES = {
    "1": "🚗 Авто выкуплен (на базе)",
    "2": "🚢 Отправлен в порт г. Пусан на погрузку",
    "3": "🌊 В пути во Владивосток",
    "4": "🛃 Таможенная очистка",
    "5": "📦 Погрузка до МСК",
    "6": "🚛 Доставляется клиенту",
}
```

### 3. Subscription & Limits

**Free Tier:**
- 3 free car calculations
- After 3 calculations, user must subscribe
- Tracked in `calculations` table

**Paid Tier:**
- Unlimited calculations
- Managers automatically have free access

**Implementation:**

```python
FREE_ACCESS_USERS = {728438182, 627689711}  # Manager IDs

def check_calculation_limit(user_id):
    if user_id in FREE_ACCESS_USERS:
        return True

    if check_user_subscription(user_id):
        return True

    count = get_calculation_count(user_id)
    return count < 3
```

### 4. Currency Exchange Rates

**Supported Currencies:**
- USD → KRW (US Dollar to Korean Won)
- USD → RUB (US Dollar to Russian Ruble)
- USDT → KRW (Tether to Korean Won)
- KRW → RUB (Korean Won to Russian Ruble)

**Data Sources:**
- CBR API for RUB rates
- Real-time market data for crypto rates

**Update Frequency:**
- Rates fetched on `/start` command
- Can be checked with `/exchange_rates`

### 5. Web Scraping & Automation

**Encar Integration:**

```python
# API endpoint for car details
url = f"https://api.encar.com/v1/readside/vehicle/{car_id}"

# Response includes:
# - Car specifications (make, model, year, mileage, etc.)
# - Pricing information
# - Photo URLs (up to 10)
# - Technical details (engine, transmission, body type)
```

**Customs Calculation:**

```python
# calcus.ru API
url = "https://calcus.ru/calculate/Customs"
payload = {
    "owner": 1,              # Individual
    "age": "0-3",            # Car age category
    "engine": 1,             # Engine type (1=petrol, 2=diesel, etc.)
    "value": engine_volume,  # cc
    "price": car_price,      # KRW
    "curr": "KRW",
}
```

**Anti-Detection Measures:**
- Rotating User-Agent headers
- Proxy support (configured in utils.py)
- Undetected ChromeDriver for Selenium
- Request delays to avoid rate limiting

---

## Code Structure & Patterns

### Main Bot Logic (main.py)

**Global State Variables:**
```python
car_data = {}              # Current car being calculated
pending_orders = {}        # Orders awaiting phone/name
user_contacts = {}         # User phone numbers
user_names = {}            # User full names
last_error_message_id = {} # For error message cleanup
```

**Command Handler Pattern:**
```python
@bot.message_handler(commands=['command_name'])
def handle_command(message):
    user_id = message.chat.id
    # Handler logic
    bot.send_message(user_id, response, reply_markup=keyboard)
```

**Callback Query Pattern:**
```python
@bot.callback_query_handler(func=lambda call: call.data.startswith('prefix_'))
def handle_callback(call):
    user_id = call.message.chat.id
    data = call.data.split('_')[-1]  # Extract ID or parameter
    # Handler logic
    bot.answer_callback_query(call.id, "✅ Success")
```

### Database Operations (database.py)

**Connection Pattern:**
```python
def connect_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# Context manager usage
with connect_db() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT ...")
        results = cur.fetchall()
    conn.commit()
```

**CRUD Operations:**
- `add_order(order)` - Insert new order
- `get_orders(user_id)` - Retrieve user orders
- `update_order_status_in_db(order_id, status)` - Update status
- `delete_order_from_db(order_id)` - Delete order

### Utility Functions (utils.py)

**Customs Calculation:**
```python
def get_customs_fees(engine_volume, car_price, car_year, car_month, engine_type=1):
    # Calculate car age category
    age = calculate_age(car_year, car_month)

    # API request to calcus.ru
    response = requests.post(url, data=payload, headers=headers)

    return response.json()
```

**Number Formatting:**
```python
def format_number(number):
    return locale.format_string("%d", number, grouping=True)
    # Example: 1000000 → "1,000,000"
```

---

## Development Guidelines

### Code Quality Standards

1. **PEP 8 Compliance**
   - Use 4 spaces for indentation
   - Max line length: 79 characters for code, 72 for comments
   - Use snake_case for functions and variables
   - Use PascalCase for classes

2. **Documentation**
   - Add docstrings to all functions
   - Include type hints where appropriate
   - Comment complex logic

3. **Error Handling**
   ```python
   try:
       # Risky operation
       response = requests.get(url)
       response.raise_for_status()
   except requests.RequestException as e:
       logging.error(f"Request failed: {e}")
       bot.send_message(user_id, "❌ Ошибка при загрузке данных")
   ```

4. **Logging**
   ```python
   import logging

   logging.basicConfig(level=logging.INFO)
   logging.info("Operation successful")
   logging.error("Error occurred", exc_info=True)
   ```

### Security Best Practices

1. **Environment Variables**
   - Never commit `.env` file
   - Use `os.getenv()` for sensitive data
   - Validate all environment variables at startup

2. **User Input Validation**
   ```python
   # Validate URL before processing
   if not ("encar.com" in url or "kbchachacha.com" in url):
       bot.send_message(user_id, "❌ Неподдерживаемый сайт")
       return

   # Sanitize phone numbers
   phone = re.sub(r'[^\d+]', '', phone_number)
   ```

3. **SQL Injection Prevention**
   - Always use parameterized queries
   ```python
   # ✅ GOOD
   cur.execute("SELECT * FROM orders WHERE user_id = %s", (user_id,))

   # ❌ BAD
   cur.execute(f"SELECT * FROM orders WHERE user_id = {user_id}")
   ```

4. **Access Control**
   ```python
   MANAGERS = [728438182, 627689711]

   def is_manager(user_id):
       return user_id in MANAGERS

   # Check before executing manager commands
   if not is_manager(message.from_user.id):
       bot.send_message(message.chat.id, "❌ Доступ запрещён")
       return
   ```

### Testing Approach

1. **Manual Testing Checklist**
   - [ ] Test `/start` command with new user
   - [ ] Test car calculation with each supported website
   - [ ] Test subscription limits
   - [ ] Test order placement flow
   - [ ] Test manager commands
   - [ ] Test error handling (invalid URLs, API failures)

2. **Database Testing**
   - Verify user creation
   - Check order insertion and retrieval
   - Test calculation count increments
   - Verify subscription status changes

3. **Integration Testing**
   - Test currency exchange API
   - Test customs calculation API
   - Test car data extraction from each source

### Common Patterns to Follow

1. **Keyboard Creation**
   ```python
   keyboard = types.InlineKeyboardMarkup()
   keyboard.add(
       types.InlineKeyboardButton("Button Text", callback_data="action_data")
   )
   keyboard.add(
       types.InlineKeyboardButton("URL Button", url="https://example.com")
   )
   ```

2. **User Data Persistence**
   ```python
   # Store temporary data
   pending_orders[user_id] = car_id

   # Retrieve and cleanup
   car_id = pending_orders.pop(user_id, None)
   ```

3. **Manager Notifications**
   ```python
   for manager_id in MANAGERS:
       bot.send_message(manager_id, message_text, parse_mode="Markdown")
   ```

4. **Error Message Management**
   ```python
   # Delete previous error message
   if last_error_message_id.get(user_id):
       try:
           bot.delete_message(user_id, last_error_message_id[user_id])
       except:
           pass

   # Send new error
   error_msg = bot.send_message(user_id, error_text)
   last_error_message_id[user_id] = error_msg.id
   ```

---

## API Integrations

### 1. Telegram Bot API

**Library**: pyTelegramBotAPI (telebot)

**Key Methods:**
- `bot.send_message()` - Send text message
- `bot.send_photo()` - Send image
- `bot.send_media_group()` - Send multiple images
- `bot.answer_callback_query()` - Respond to button clicks
- `bot.edit_message_text()` - Edit existing message
- `bot.delete_message()` - Delete message

### 2. Encar API

**Base URL**: `https://api.encar.com/v1/readside/vehicle/{car_id}`

**Authentication**: None required

**Response Structure**:
```json
{
  "category": {
    "manufacturerEnglishName": "Toyota",
    "modelGroupEnglishName": "Camry",
    "gradeDetailEnglishName": "Premium",
    "yearMonth": "202010"
  },
  "advertisement": {
    "price": 15000000
  },
  "spec": {
    "mileage": 50000,
    "transmissionName": "오토",
    "displacement": 2000,
    "bodyName": "세단"
  },
  "photos": [
    {"path": "carpicture02/pic3902/39027097_001.jpg"},
    ...
  ]
}
```

### 3. Calcus.ru Customs API

**Endpoint**: `https://calcus.ru/calculate/Customs`

**Method**: POST

**Payload**:
```python
{
    "owner": 1,              # 1 = individual, 2 = legal entity
    "age": "0-3",            # Car age: "0-3", "3-5", "5-7", "7-0"
    "engine": 1,             # 1=petrol, 2=diesel, 3=hybrid, 4=electric
    "power": 1,              # Engine power (can use default 1)
    "power_unit": 1,         # 1 = horsepower
    "value": 2000,           # Engine volume in cc
    "price": 15000000,       # Car price in KRW
    "curr": "KRW"            # Currency code
}
```

**Response**: JSON with calculated customs fees

### 4. Currency Exchange APIs

**Implementation**: Custom functions in main.py

Functions:
- `get_usd_to_krw_rate()` - USD to Korean Won
- `get_usd_to_rub_rate()` - USD to Russian Ruble
- `get_usdt_to_krw_rate()` - USDT to Korean Won
- `get_rub_to_krw_rate()` - RUB to Korean Won

---

## Troubleshooting

### Common Issues

1. **Bot not responding**
   - Check if bot process is running
   - Verify BOT_TOKEN in environment variables
   - Check network connectivity
   - Review logs in `bot.log`

2. **Database connection errors**
   - Verify DATABASE_URL is correct
   - Check PostgreSQL service is running
   - Ensure database tables are created (`create_tables()`)

3. **Car data extraction fails**
   - Website structure may have changed
   - Check if car URL is valid
   - Verify API endpoints are accessible
   - Check for rate limiting or blocking

4. **Customs calculation returns None**
   - calcus.ru API may be down
   - Check proxy configuration
   - Verify payload parameters are correct
   - Increase timeout/retry logic

5. **Currency rates not updating**
   - External API may be unavailable
   - Check network connectivity
   - Verify API endpoints are still valid

### Debugging Tips

1. **Enable verbose logging**
   ```python
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Add print statements**
   ```python
   print(f"✅ Car data: {car_data}")
   print(f"❌ Error: {error_message}")
   ```

3. **Test database queries directly**
   ```python
   with connect_db() as conn:
       with conn.cursor() as cur:
           cur.execute("SELECT COUNT(*) FROM orders;")
           print(cur.fetchone())
   ```

4. **Test API endpoints manually**
   ```bash
   curl -X POST https://calcus.ru/calculate/Customs \
     -d "owner=1&age=0-3&engine=1&value=2000&price=15000000&curr=KRW"
   ```

---

## Deployment Checklist

### Pre-deployment

- [ ] All tests passing
- [ ] Environment variables configured
- [ ] Database migrations applied
- [ ] `.env` file not in git
- [ ] Dependencies updated in `requirements.txt`
- [ ] Python version specified in `runtime.txt`

### Heroku Deployment

1. **Create Heroku app**
   ```bash
   heroku create deytrading-bot
   ```

2. **Add PostgreSQL addon**
   ```bash
   heroku addons:create heroku-postgresql:mini
   ```

3. **Set environment variables**
   ```bash
   heroku config:set BOT_TOKEN=your_token_here
   ```

4. **Deploy**
   ```bash
   git push heroku main
   ```

5. **Scale worker**
   ```bash
   heroku ps:scale worker=1
   ```

6. **Initialize database**
   ```bash
   heroku run python -c "from database import create_tables; create_tables()"
   ```

### Post-deployment

- [ ] Verify bot responds to `/start`
- [ ] Test car calculation
- [ ] Check database connections
- [ ] Monitor logs: `heroku logs --tail`
- [ ] Test manager commands
- [ ] Verify currency rates update

---

## Future Enhancements

### Potential Features

1. **Payment Integration**
   - Accept payments directly in bot
   - Subscription management via Stripe/PayPal
   - Automatic subscription renewal

2. **Advanced Search**
   - Filter cars by make/model/year
   - Price range search
   - Notification when matching cars appear

3. **Analytics Dashboard**
   - User engagement metrics
   - Popular car models
   - Conversion rates (calculations → orders)

4. **Multi-language Support**
   - English interface
   - Korean interface
   - Automatic language detection

5. **Automated Status Updates**
   - Track shipment automatically
   - Push notifications on status changes
   - Integration with shipping APIs

6. **Image Recognition**
   - Upload car photo to identify make/model
   - Damage assessment from photos
   - VIN number extraction

---

## Contact & Support

**Managers:**
- Андрей: +82-10-8855-0386
- Telegram: @DeyTrading6

**Channel:**
- @dey_trading

**Technical Support:**
- Review logs in `bot.log`
- Check Heroku dashboard
- Monitor database performance

---

## Version History

**Current Version**: Production (as of October 2025)

**Key Updates:**
- **October 2025**:
  - ✅ Fixed critical JSONDecodeError crashes in all API calls
  - ✅ Added comprehensive error handling for Encar API
  - ✅ Added timeout protection (10 seconds) to all HTTP requests
  - ✅ Implemented fallback rates for currency exchange APIs
  - ✅ Added proper logging for all API failures
  - ✅ Improved user-friendly error messages
- Added subscription system with calculation limits
- Implemented manager tools for order management
- Enhanced error handling and logging
- Added support for multiple car marketplaces
- Integrated real-time currency exchange rates
- Improved user tracking and analytics

### Recent Bug Fixes (October 2025)

**Critical Fix: JSONDecodeError Prevention**

The bot was crashing with `requests.exceptions.JSONDecodeError: Expecting value: line 1 column 1 (char 0)` when external APIs returned non-JSON responses. The following fixes were implemented:

**Functions Fixed:**
1. `get_car_info()` (line ~1115) - Encar API car data fetching
2. `is_user_subscribed()` (line ~865) - Telegram subscription check
3. `get_usdt_to_krw_rate()` (line ~920) - Coinbase currency API
4. `get_rub_to_krw_rate()` (line ~956) - Currency API for RUB→KRW ⚠️ **Critical startup fix**
5. `get_usd_to_krw_rate()` (line ~994) - Manana currency API
6. `get_usd_to_rub_rate()` (line ~1026) - Mosca currency API
7. `get_insurance_total()` (line ~2153) - Encar insurance data
8. `get_technical_card()` (line ~2206) - Encar technical report

**Error Handling Pattern:**
```python
try:
    response = requests.get(url, headers=headers, timeout=10)

    # Check status code
    if response.status_code != 200:
        logging.error(f"API returned status {response.status_code}")
        return None  # or fallback value

    # Parse JSON
    data = response.json()

except requests.exceptions.Timeout:
    logging.error("Timeout error")
    return fallback_value
except requests.exceptions.RequestException as e:
    logging.error(f"Request error: {e}")
    return fallback_value
except json.JSONDecodeError as e:
    logging.error(f"JSON decode error: {e}")
    return fallback_value
except (KeyError, TypeError) as e:
    logging.error(f"Data parsing error: {e}")
    return fallback_value
```

**Key Improvements:**
- ✅ All HTTP requests now have 10-second timeouts
- ✅ Status codes checked before parsing JSON
- ✅ Specific error types caught and logged separately
- ✅ Fallback values provided for currency rates
- ✅ User-friendly error messages shown to users
- ✅ Bot no longer crashes when APIs fail
- ✅ **Fixed critical startup issue**: `get_rub_to_krw_rate()` now sets fallback value instead of returning None

### Fallback Currency Rates
When external currency APIs fail, the bot uses these fallback rates to ensure it can still start:
- **USDT → KRW**: 1350.0
- **USD → KRW**: 1340.0
- **USD → RUB**: 95.0
- **RUB → KRW**: 14.0 (new)

---

## License & Legal

**Disclaimer**: This bot is for educational and business purposes. Users are responsible for complying with import regulations and customs laws in their respective countries.

**Data Privacy**: User data (phone numbers, names) is stored securely and used only for order processing purposes.

**Third-party APIs**: This bot integrates with external services (Encar, calcus.ru, etc.). Changes to these services may affect bot functionality.

---

*Last Updated: October 2025*
*Maintained by: DeyTrading Team*

# Food Ordering System on Frappe Framework

This is a custom Frappe Framework app for a restaurant food ordering system with a menu, search, category filters, user login/signup, cart system, and an AI-style food chatbot.

## Features

- Food menu
- Search foods
- Category filters
- 11 food and beverage categories
- 50 seeded food and beverage items
- Local category image assets for menu cards
- Vegan and spicy filters
- User login/signup through Frappe
- Cart system for logged-in users
- Food chatbot for nutrition and restaurant questions

## Chatbot Answers

The chatbot can answer questions about:

- Calories
- Ingredients
- Protein and carbs
- Best drinks with meals
- Spicy recommendations
- Diet suggestions
- Vegan options
- Allergies
- Restaurant timings

## Tech Stack

- Frappe Framework v15
- Python
- Frappe DocTypes
- Frappe ORM
- Frappe Website Pages
- HTML
- CSS
- JavaScript
- Jinja templates
- MariaDB / MySQL
- Redis
- Node.js, Yarn, and esbuild through Frappe Bench

## Main DocTypes

- `Food Category`
- `Food Item`
- `Food Cart Item`
- `Restaurant Settings`

## Seeded Categories

Food categories:

- Pizza
- Burgers
- Indian
- Chinese
- Desserts
- Snacks

Beverage categories:

- Soft Drinks
- Coffee
- Tea
- Mocktails
- Shakes

## Main Files

- `food_ordering/api.py` - backend APIs, cart logic, chatbot logic, sample data
- `food_ordering/www/food_menu.html` - public food menu page
- `food_ordering/www/food_menu.py` - page context
- `food_ordering/public/js/food_menu.js` - menu, filters, cart, chatbot frontend logic
- `food_ordering/public/css/food_menu.css` - page styling

## Run Locally From GitHub

These steps assume Frappe Bench is already installed.

### 1. Create A New Bench

```bash
cd ~
bench init frappe-bench --frappe-branch version-15
cd frappe-bench
```

### 2. Create A Frappe Site

```bash
bench new-site food.localhost
```

Set an Administrator password when asked.

### 3. Get This App From GitHub

Replace the URL with your GitHub repository URL:

```bash
bench get-app https://github.com/YOUR_USERNAME/food_ordering.git
```

If you downloaded the project as a ZIP instead, copy the `food_ordering` app folder into:

```text
~/frappe-bench/apps/
```

Then run:

```bash
cd ~/frappe-bench
./env/bin/pip install -e apps/food_ordering
echo food_ordering >> sites/apps.txt
```

### 4. Install The App On The Site

```bash
bench --site food.localhost install-app food_ordering
bench --site food.localhost migrate
```

### 5. Add Sample Food Data

```bash
bench --site food.localhost execute food_ordering.api.create_sample_data
```

### 6. Build Assets

```bash
bench build --app food_ordering
```

### 7. Start The Server

```bash
bench start
```

If `bench start` says `No process manager found`, install Honcho:

```bash
./env/bin/pip install honcho
```

Then run:

```bash
bench start
```

### 8. Open The App

Customer food menu:

```text
http://food.localhost:8000/food-menu
```

If your bench starts on port `8001`, open:

```text
http://food.localhost:8001/food-menu
```

Frappe admin desk:

```text
http://food.localhost:8000/app
```

Login with:

```text
Username: Administrator
Password: the password you set during bench new-site
```

## Useful Commands

Clear cache:

```bash
bench --site food.localhost clear-cache
```

Run migrations:

```bash
bench --site food.localhost migrate
```

Rebuild assets:

```bash
bench build --app food_ordering
```

Create sample data again:

```bash
bench --site food.localhost execute food_ordering.api.create_sample_data
```

## Distribute The App

Anyone can install this app into an existing Frappe Bench using:

```bash
bench get-app https://github.com/YOUR_USERNAME/food_ordering.git
bench --site SITE_NAME install-app food_ordering
bench --site SITE_NAME migrate
bench --site SITE_NAME execute food_ordering.api.create_sample_data
bench start
```

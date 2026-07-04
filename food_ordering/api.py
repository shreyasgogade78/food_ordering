import re

import frappe
from frappe import _


def _require_login():
    if frappe.session.user == "Guest":
        frappe.throw(_("Please login to use the cart"), frappe.PermissionError)


def _as_bool(value):
    return str(value).lower() in {"1", "true", "yes"}


@frappe.whitelist(allow_guest=True)
def get_categories():
    return frappe.get_all(
        "Food Category",
        fields=["name", "category_name", "description", "image"],
        order_by="category_name asc",
    )


@frappe.whitelist(allow_guest=True)
def get_menu(search=None, category=None, vegan=None, spicy=None):
    filters = {"disabled": 0}
    if category:
        filters["category"] = category
    if vegan is not None and vegan != "":
        filters["is_vegan"] = 1 if _as_bool(vegan) else 0
    if spicy is not None and spicy != "":
        filters["is_spicy"] = 1 if _as_bool(spicy) else 0

    items = frappe.get_all(
        "Food Item",
        filters=filters,
        fields=[
            "name",
            "item_name",
            "category",
            "price",
            "description",
            "image",
            "calories",
            "protein",
            "carbs",
            "ingredients",
            "allergens",
            "is_vegan",
            "is_spicy",
            "spicy_level",
            "recommended_drinks",
            "diet_tags",
        ],
        order_by="item_name asc",
    )

    if search:
        term = search.lower()
        items = [
            item
            for item in items
            if term in (item.item_name or "").lower()
            or term in (item.category or "").lower()
            or term in (item.description or "").lower()
            or term in (item.ingredients or "").lower()
            or term in (item.diet_tags or "").lower()
        ]

    return items


@frappe.whitelist()
def add_to_cart(food_item, quantity=1):
    _require_login()
    quantity = max(int(quantity or 1), 1)
    item = frappe.get_doc("Food Item", food_item)

    existing = frappe.get_all(
        "Food Cart Item",
        filters={"user": frappe.session.user, "food_item": food_item},
        fields=["name", "quantity"],
        limit=1,
    )

    if existing:
        cart_item = frappe.get_doc("Food Cart Item", existing[0].name)
        cart_item.quantity += quantity
    else:
        cart_item = frappe.new_doc("Food Cart Item")
        cart_item.user = frappe.session.user
        cart_item.food_item = food_item
        cart_item.quantity = quantity
        cart_item.price = item.price

    cart_item.save(ignore_permissions=True)
    frappe.db.commit()
    return get_cart()


@frappe.whitelist()
def update_cart_item(cart_item, quantity):
    _require_login()
    quantity = int(quantity)
    doc = frappe.get_doc("Food Cart Item", cart_item)
    if doc.user != frappe.session.user:
        frappe.throw(_("You cannot update another user's cart"))

    if quantity <= 0:
        frappe.delete_doc("Food Cart Item", doc.name, ignore_permissions=True)
    else:
        doc.quantity = quantity
        doc.save(ignore_permissions=True)

    frappe.db.commit()
    return get_cart()


@frappe.whitelist()
def remove_from_cart(cart_item):
    _require_login()
    doc = frappe.get_doc("Food Cart Item", cart_item)
    if doc.user != frappe.session.user:
        frappe.throw(_("You cannot remove another user's cart item"))

    frappe.delete_doc("Food Cart Item", doc.name, ignore_permissions=True)
    frappe.db.commit()
    return get_cart()


@frappe.whitelist()
def clear_cart():
    _require_login()
    for row in frappe.get_all("Food Cart Item", filters={"user": frappe.session.user}, pluck="name"):
        frappe.delete_doc("Food Cart Item", row, ignore_permissions=True)
    frappe.db.commit()
    return get_cart()


@frappe.whitelist()
def get_cart():
    _require_login()
    rows = frappe.get_all(
        "Food Cart Item",
        filters={"user": frappe.session.user},
        fields=["name", "food_item", "quantity", "price", "amount"],
        order_by="creation desc",
    )

    total = 0
    for row in rows:
        row.item_name = frappe.db.get_value("Food Item", row.food_item, "item_name")
        total += row.amount or 0

    return {"items": rows, "total": total}


@frappe.whitelist(allow_guest=True)
def chatbot(message):
    question = (message or "").strip()
    if not question:
        return {"answer": "Ask me about calories, ingredients, protein, carbs, drinks, spice, vegan food, allergies, diets, or restaurant timings."}

    lower = question.lower()
    item = _find_food_item(lower)

    if _matches(lower, "timing", "time", "open", "close", "hours"):
        return {"answer": _restaurant_timings_answer()}

    if _matches(lower, "vegan"):
        return {"answer": _list_items({"is_vegan": 1}, "Vegan options")}

    if _matches(lower, "spicy", "hot"):
        return {"answer": _list_items({"is_spicy": 1}, "Spicy recommendations")}

    if _matches(lower, "diet", "healthy", "fitness", "low calorie", "weight loss"):
        return {"answer": _diet_answer()}

    if item:
        if _matches(lower, "calorie", "calories", "kcal"):
            return {"answer": f"{item.item_name} has about {item.calories or 0} calories."}
        if _matches(lower, "ingredient", "ingredients", "made"):
            return {"answer": f"{item.item_name} ingredients: {item.ingredients or 'Ingredients are not updated yet.'}"}
        if _matches(lower, "protein", "carb", "carbs", "nutrition", "macro"):
            return {"answer": f"{item.item_name} has {item.protein or 0}g protein and {item.carbs or 0}g carbs."}
        if _matches(lower, "drink", "drinks", "beverage"):
            return {"answer": f"Best drinks with {item.item_name}: {item.recommended_drinks or 'Water, lemonade, or iced tea.'}"}
        if _matches(lower, "allergy", "allergies", "allergen", "allergens"):
            return {"answer": f"{item.item_name} allergens: {item.allergens or 'No allergen information listed.'}"}
        if _matches(lower, "vegan"):
            return {"answer": f"{item.item_name} is {'vegan' if item.is_vegan else 'not marked as vegan'}."}
        if _matches(lower, "spicy", "hot"):
            level = item.spicy_level or ("spicy" if item.is_spicy else "not spicy")
            return {"answer": f"{item.item_name} spice level: {level}."}
        return {"answer": _item_summary(item)}

    if _matches(lower, "calorie", "protein", "carb", "ingredient", "allergy", "drink"):
        return {"answer": "Please mention a food name, for example: calories in Paneer Tikka or ingredients of Veg Burger."}

    return {"answer": "I can help with calories, ingredients, protein/carbs, drinks, spicy food, vegan options, allergies, diet suggestions, and restaurant timings."}


def _matches(text, *words):
    return any(word in text for word in words)


def _find_food_item(text):
    items = frappe.get_all(
        "Food Item",
        filters={"disabled": 0},
        fields=[
            "name",
            "item_name",
            "category",
            "price",
            "description",
            "calories",
            "protein",
            "carbs",
            "ingredients",
            "allergens",
            "is_vegan",
            "is_spicy",
            "spicy_level",
            "recommended_drinks",
            "diet_tags",
        ],
    )

    cleaned = re.sub(r"[^a-z0-9 ]", " ", text)
    for item in items:
        item_name = (item.item_name or "").lower()
        if item_name and item_name in cleaned:
            return item

    for item in items:
        words = [word for word in (item.item_name or "").lower().split() if len(word) > 2]
        if words and all(word in cleaned for word in words):
            return item

    return None


def _restaurant_timings_answer():
    settings = frappe.get_single("Restaurant Settings")
    opening = settings.opening_time or "10:00:00"
    closing = settings.closing_time or "22:00:00"
    return f"{settings.restaurant_name or 'The restaurant'} is open from {opening} to {closing}."


def _list_items(filters, title):
    items = frappe.get_all("Food Item", filters={**filters, "disabled": 0}, fields=["item_name", "spicy_level"], limit=10)
    if not items:
        return f"No {title.lower()} are available right now."
    names = []
    for item in items:
        suffix = f" ({item.spicy_level})" if item.spicy_level and filters.get("is_spicy") else ""
        names.append(f"{item.item_name}{suffix}")
    return f"{title}: " + ", ".join(names)


def _diet_answer():
    items = frappe.get_all(
        "Food Item",
        filters={"disabled": 0},
        fields=["item_name", "calories", "protein", "diet_tags"],
        order_by="calories asc",
        limit=5,
    )
    if not items:
        return "No food items are available for diet suggestions yet."
    names = [f"{item.item_name} ({item.calories or 0} cal, {item.protein or 0}g protein)" for item in items]
    return "For a lighter diet, try: " + ", ".join(names)


def _item_summary(item):
    vegan = "vegan" if item.is_vegan else "non-vegan"
    spicy = f", {item.spicy_level.lower()} spicy" if item.spicy_level else ""
    return f"{item.item_name} is a {vegan}{spicy} item with {item.calories or 0} calories, {item.protein or 0}g protein, and {item.carbs or 0}g carbs."


@frappe.whitelist()
def create_sample_data():
    category_descriptions = {
        "Pizza": "Hand-tossed pizzas with classic and modern toppings.",
        "Burgers": "Loaded burgers with vegetarian and chicken options.",
        "Indian": "Indian curries, rice bowls, and tandoori favorites.",
        "Chinese": "Noodles, rice, and Indo-Chinese comfort food.",
        "Desserts": "Sweet dishes, cakes, brownies, and chilled desserts.",
        "Snacks": "Quick bites, fried snacks, and street-food favorites.",
        "Soft Drinks": "Classic fizzy and chilled bottled drinks.",
        "Coffee": "Hot and cold coffee beverages.",
        "Tea": "Indian chai and flavored tea beverages.",
        "Mocktails": "Refreshing non-alcoholic mixed drinks.",
        "Shakes": "Thick milkshakes and dessert-style beverages.",
    }

    category_images = {
        category: f"/assets/food_ordering/images/{category.lower().replace(' ', '-')}.svg"
        for category in category_descriptions
    }

    for category, description in category_descriptions.items():
        if frappe.db.exists("Food Category", category):
            doc = frappe.get_doc("Food Category", category)
        else:
            doc = frappe.new_doc("Food Category")
            doc.category_name = category
        doc.description = description
        doc.image = category_images[category]
        doc.save(ignore_permissions=True)

    def item(name, category, price, calories, protein, carbs, ingredients, allergens, vegan, spicy, spice, drinks, tags):
        return {
            "item_name": name,
            "category": category,
            "price": price,
            "description": f"{name} from our {category} menu.",
            "image": category_images[category],
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "ingredients": ingredients,
            "allergens": allergens,
            "is_vegan": 1 if vegan else 0,
            "is_spicy": 1 if spicy else 0,
            "spicy_level": spice if spicy else "",
            "recommended_drinks": drinks,
            "diet_tags": tags,
            "disabled": 0,
        }

    items = [
        item("Margherita Pizza", "Pizza", 199, 610, 24, 78, "Pizza base, tomato sauce, mozzarella, basil", "Gluten, dairy", False, False, "", "Lemon iced tea, cola", "vegetarian, classic"),
        item("Farmhouse Pizza", "Pizza", 279, 720, 28, 86, "Pizza base, cheese, onion, capsicum, mushroom, corn", "Gluten, dairy", False, False, "", "Mint mojito, cola", "vegetarian"),
        item("Paneer Tikka Pizza", "Pizza", 299, 760, 32, 82, "Pizza base, paneer tikka, cheese, onion, capsicum", "Gluten, dairy", False, True, "Medium", "Sweet lime soda, cold coffee", "vegetarian, high protein"),
        item("Pepperoni Pizza", "Pizza", 349, 820, 36, 74, "Pizza base, pepperoni, cheese, tomato sauce", "Gluten, dairy", False, True, "Mild", "Cola, iced tea", "non-vegetarian"),
        item("Veggie Supreme Pizza", "Pizza", 319, 740, 30, 88, "Pizza base, cheese, olives, jalapeno, tomato, onion", "Gluten, dairy", False, True, "Medium", "Blue lagoon, lemon soda", "vegetarian"),
        item("Chicken BBQ Pizza", "Pizza", 379, 850, 42, 80, "Pizza base, BBQ chicken, cheese, onion, bell pepper", "Gluten, dairy", False, True, "Mild", "Cola, peach iced tea", "non-vegetarian, high protein"),
        item("Classic Veg Burger", "Burgers", 149, 430, 12, 58, "Burger bun, vegetable patty, lettuce, tomato, sauce", "Gluten", False, False, "", "Cola, iced tea", "vegetarian"),
        item("Cheese Burger", "Burgers", 179, 520, 18, 54, "Burger bun, patty, cheese slice, lettuce, mayo", "Gluten, dairy", False, False, "", "Cold coffee, cola", "vegetarian"),
        item("Paneer Makhani Burger", "Burgers", 199, 560, 22, 52, "Burger bun, paneer patty, makhani sauce, onion", "Gluten, dairy", False, True, "Medium", "Sweet lassi, lemon soda", "vegetarian"),
        item("Crispy Chicken Burger", "Burgers", 219, 610, 31, 56, "Burger bun, fried chicken, lettuce, mayo", "Gluten, egg", False, True, "Mild", "Cola, iced tea", "non-vegetarian"),
        item("Aloo Tikki Burger", "Burgers", 129, 390, 8, 62, "Burger bun, potato patty, onion, chutney", "Gluten", False, True, "Medium", "Masala tea, lemon soda", "vegetarian"),
        item("Mushroom Swiss Burger", "Burgers", 229, 540, 20, 48, "Burger bun, mushroom patty, swiss cheese, sauce", "Gluten, dairy", False, False, "", "Cold coffee, cola", "vegetarian"),
        item("Paneer Butter Masala", "Indian", 249, 480, 22, 28, "Paneer, tomato gravy, butter, cream, spices", "Dairy", False, True, "Medium", "Butter milk, sweet lassi", "vegetarian, high protein"),
        item("Dal Makhani", "Indian", 219, 420, 18, 46, "Black lentils, kidney beans, butter, cream", "Dairy", False, False, "", "Jeera soda, butter milk", "vegetarian, protein"),
        item("Veg Biryani", "Indian", 239, 560, 12, 92, "Basmati rice, vegetables, spices, saffron", "None", True, True, "Medium", "Raita, lemon soda", "vegan, rice"),
        item("Chicken Biryani", "Indian", 299, 680, 38, 78, "Basmati rice, chicken, spices, fried onion", "None", False, True, "Hot", "Mint mojito, cola", "non-vegetarian, high protein"),
        item("Chole Bhature", "Indian", 189, 720, 20, 96, "Chickpeas, flour, spices, onion, tomato", "Gluten", False, True, "Medium", "Sweet lassi, masala tea", "vegetarian"),
        item("Masala Dosa", "Indian", 159, 410, 9, 72, "Rice batter, potato masala, chutney, sambar", "None", True, True, "Mild", "Filter coffee, tea", "vegan, south indian"),
        item("Tandoori Chicken", "Indian", 329, 520, 48, 10, "Chicken, curd, tandoori spices, lemon", "Dairy", False, True, "Hot", "Mint mojito, cola", "non-vegetarian, high protein"),
        item("Veg Hakka Noodles", "Chinese", 179, 520, 13, 82, "Noodles, cabbage, carrot, capsicum, soy sauce", "Gluten, soy", True, True, "Medium", "Lemon iced tea, cola", "vegan"),
        item("Schezwan Noodles", "Chinese", 199, 560, 14, 84, "Noodles, schezwan sauce, vegetables, garlic", "Gluten, soy", True, True, "Hot", "Blue lagoon, cola", "vegan, spicy"),
        item("Veg Manchurian", "Chinese", 189, 440, 10, 58, "Vegetable balls, soy sauce, garlic, spring onion", "Gluten, soy", True, True, "Medium", "Lemon soda, iced tea", "vegan"),
        item("Chicken Fried Rice", "Chinese", 229, 590, 30, 74, "Rice, chicken, egg, spring onion, soy sauce", "Egg, soy", False, True, "Mild", "Cola, peach iced tea", "non-vegetarian"),
        item("Chilli Paneer", "Chinese", 219, 510, 24, 42, "Paneer, capsicum, onion, chilli sauce, soy", "Dairy, soy", False, True, "Hot", "Lemon soda, mint mojito", "vegetarian, high protein"),
        item("Spring Rolls", "Chinese", 149, 360, 8, 48, "Roll sheets, cabbage, carrot, noodles, sauce", "Gluten, soy", True, True, "Mild", "Tea, cola", "vegan, snack"),
        item("Chocolate Brownie", "Desserts", 129, 390, 6, 48, "Chocolate, flour, butter, sugar", "Gluten, dairy", False, False, "", "Cold coffee, vanilla shake", "dessert"),
        item("Gulab Jamun", "Desserts", 99, 310, 5, 52, "Khoya, flour, sugar syrup, cardamom", "Dairy, gluten", False, False, "", "Masala tea", "dessert, indian sweet"),
        item("Cheesecake Slice", "Desserts", 179, 430, 8, 46, "Cream cheese, biscuit base, sugar, vanilla", "Dairy, gluten", False, False, "", "Americano, coffee", "dessert"),
        item("Ice Cream Sundae", "Desserts", 159, 460, 7, 60, "Ice cream, chocolate sauce, nuts, wafer", "Dairy, nuts, gluten", False, False, "", "Cold coffee", "dessert"),
        item("Rasmalai", "Desserts", 149, 330, 10, 38, "Paneer dumplings, milk, saffron, pistachio", "Dairy, nuts", False, False, "", "Tea", "dessert, indian sweet"),
        item("Samosa", "Snacks", 49, 260, 5, 34, "Potato filling, flour, peas, spices", "Gluten", False, True, "Medium", "Masala tea", "vegetarian, snack"),
        item("French Fries", "Snacks", 99, 330, 4, 42, "Potato, salt, seasoning", "None", True, False, "", "Cola, shake", "vegan, snack"),
        item("Paneer Pakora", "Snacks", 139, 370, 16, 28, "Paneer, gram flour, spices, chutney", "Dairy", False, True, "Mild", "Tea, lemon soda", "vegetarian"),
        item("Pav Bhaji", "Snacks", 149, 430, 10, 64, "Pav, vegetable mash, butter, spices", "Gluten, dairy", False, True, "Medium", "Masala soda", "vegetarian, street food"),
        item("Nachos with Salsa", "Snacks", 169, 410, 9, 54, "Corn chips, salsa, jalapeno, cheese sauce", "Dairy", False, True, "Mild", "Mocktail, cola", "vegetarian"),
        item("Classic Cola", "Soft Drinks", 59, 140, 0, 36, "Carbonated water, sugar, cola flavor", "None", True, False, "", "Pairs with burgers and pizza", "beverage, vegan"),
        item("Lemon Soda", "Soft Drinks", 69, 110, 0, 28, "Soda, lemon juice, sugar, salt", "None", True, False, "", "Pairs with spicy food", "beverage, vegan"),
        item("Orange Fizz", "Soft Drinks", 79, 130, 0, 32, "Orange syrup, soda, ice", "None", True, False, "", "Pairs with snacks", "beverage, vegan"),
        item("Cappuccino", "Coffee", 129, 120, 6, 12, "Espresso, steamed milk, foam", "Dairy", False, False, "", "Pairs with desserts", "coffee"),
        item("Cold Coffee", "Coffee", 149, 240, 7, 34, "Coffee, milk, sugar, ice cream", "Dairy", False, False, "", "Pairs with burgers and brownies", "coffee, cold"),
        item("Americano", "Coffee", 99, 15, 0, 2, "Espresso, hot water", "None", True, False, "", "Pairs with cheesecake", "coffee, vegan, low calorie"),
        item("Masala Tea", "Tea", 49, 90, 3, 14, "Tea, milk, ginger, cardamom, spices", "Dairy", False, False, "", "Pairs with samosa and pakora", "tea"),
        item("Lemon Tea", "Tea", 59, 45, 0, 10, "Tea, lemon, honey, hot water", "None", True, False, "", "Pairs with snacks", "tea, vegan"),
        item("Iced Peach Tea", "Tea", 99, 120, 0, 30, "Black tea, peach syrup, ice", "None", True, False, "", "Pairs with pizza and burgers", "tea, cold, vegan"),
        item("Virgin Mojito", "Mocktails", 129, 130, 0, 34, "Mint, lemon, soda, sugar, ice", "None", True, False, "", "Pairs with Indian and Chinese", "mocktail, vegan"),
        item("Blue Lagoon", "Mocktails", 139, 150, 0, 38, "Blue curacao syrup, lemon, soda, ice", "None", True, False, "", "Pairs with spicy food", "mocktail, vegan"),
        item("Watermelon Cooler", "Mocktails", 149, 120, 1, 30, "Watermelon, lemon, mint, ice", "None", True, False, "", "Pairs with snacks and pizza", "mocktail, vegan"),
        item("Chocolate Shake", "Shakes", 159, 420, 10, 58, "Milk, chocolate syrup, ice cream", "Dairy", False, False, "", "Pairs with fries and burgers", "shake"),
        item("Mango Shake", "Shakes", 149, 330, 8, 52, "Mango, milk, sugar, ice", "Dairy", False, False, "", "Pairs with Indian food", "shake"),
        item("Oreo Shake", "Shakes", 179, 480, 9, 66, "Milk, Oreo cookies, ice cream", "Dairy, gluten", False, False, "", "Pairs with desserts", "shake, dessert"),
    ]

    for data in items:
        if frappe.db.exists("Food Item", data["item_name"]):
            doc = frappe.get_doc("Food Item", data["item_name"])
        else:
            doc = frappe.new_doc("Food Item")
        doc.update(data)
        doc.save(ignore_permissions=True)

    settings = frappe.get_single("Restaurant Settings")
    settings.restaurant_name = "Fresh Bite Restaurant"
    settings.opening_time = "10:00:00"
    settings.closing_time = "22:00:00"
    settings.save(ignore_permissions=True)

    frappe.db.commit()
    return f"Sample food ordering data created or updated with {len(category_descriptions)} categories and {len(items)} items"

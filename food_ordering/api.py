import re
import zlib
from urllib.parse import quote

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


# ---------------------------------------------------------------------------
# Chatbot
# ---------------------------------------------------------------------------

GREETING_WORDS = ("hi", "hii", "hello", "hey", "namaste", "good morning", "good afternoon", "good evening")
THANKS_WORDS = ("thank you", "thanks", "thank u", "thnx", "great", "awesome")
FAREWELL_WORDS = ("bye", "goodbye", "see you", "good night", "take care")

ADD_TO_CART_PHRASES = (
    "add to cart",
    "add it to cart",
    "add it to my cart",
    "add to my cart",
    "order it",
    "buy it",
    "i want to order",
    "i would like to order",
    "i'd like to order",
)

REMOVE_FROM_CART_PHRASES = ("remove", "delete", "take out", "cancel")

NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "single": 1,
    "couple": 2,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


@frappe.whitelist(allow_guest=True)
def chatbot(message):
    question = (message or "").strip()
    if not question:
        return {"answer": _help_answer()}

    lower = question.lower()

    # --- small talk -------------------------------------------------------
    if _matches(lower, *GREETING_WORDS):
        return {"answer": _greeting_answer()}

    if _matches(lower, *FAREWELL_WORDS):
        return {"answer": "Goodbye! Have a delicious day. 🍽️"}

    if _matches(lower, *THANKS_WORDS) and not _find_food_item(lower):
        return {"answer": "You're welcome! Anything else I can help you order?"}

    # --- restaurant info ---------------------------------------------------
    if _matches(lower, "timing", "time", "open", "close", "hours"):
        return {"answer": _restaurant_timings_answer()}

    if _matches(lower, "delivery", "deliver", "shipping"):
        return {"answer": _delivery_answer()}

    # --- browsing / discovery ----------------------------------------------
    # Check for a specific category ("pizza menu", "show desserts") BEFORE the
    # generic "menu" keyword, otherwise the generic check always wins and a
    # request like "show me the pizza menu" incorrectly lists all categories
    # instead of pizza items.
    category = _find_category(lower)
    if category and _matches(
        lower, "show", "list", "what", "items", "have", "menu", "give me", "any"
    ):
        return {"answer": _category_items_answer(category)}

    if _matches(
        lower,
        "menu",
        "categories",
        "category list",
        "full menu",
        "what do you have",
        "what do you serve",
        "what's available",
        "what is available",
    ):
        return {"answer": _list_categories_answer()}

    price_range_answer = _price_range_answer(lower)
    if price_range_answer:
        return {"answer": price_range_answer}

    if _matches(lower, "vegan"):
        return {"answer": _list_items({"is_vegan": 1}, "Vegan options")}

    if _matches(lower, "spicy", "hot"):
        return {"answer": _list_items({"is_spicy": 1}, "Spicy recommendations")}

    if _matches(lower, "diet", "healthy", "fitness", "low calorie", "weight loss"):
        return {"answer": _diet_answer()}

    if _matches(
        lower,
        "recommend",
        "suggest",
        "popular",
        "best seller",
        "bestseller",
        "special",
        "what should i eat",
        "what should i order",
        "chef's pick",
        "anything good",
    ):
        return {"answer": _recommend_items_answer()}

    # --- cart & checkout -----------------------------------------------------
    if _matches(lower, "cart", "my order") and _matches(lower, "what", "show", "view", "total", "check", "in my"):
        return {"answer": _cart_summary_answer()}

    if _matches(lower, "checkout", "place order", "place my order", "confirm order", "pay"):
        return {"answer": _checkout_answer()}

    if _matches(lower, "clear cart", "empty cart", "empty my cart"):
        return {"answer": _clear_cart_answer()}

    # --- item specific -------------------------------------------------------
    item = _find_food_item(lower)

    if item and _wants_remove(lower):
        return {"answer": _chat_remove_from_cart_answer(item)}

    if item and _wants_add(lower):
        quantity = _extract_quantity(lower)
        return {"answer": _chat_add_to_cart_answer(item, quantity)}

    if item:
        if _matches(lower, "calorie", "calories", "kcal"):
            return {"answer": f"{item.item_name} has about {item.calories or 0} calories."}
        if _matches(lower, "ingredient", "ingredients", "made"):
            return {"answer": f"{item.item_name} ingredients: {item.ingredients or 'Ingredients are not updated yet.'}"}
        if _matches(lower, "protein", "carb", "carbs", "nutrition", "macro"):
            return {"answer": f"{item.item_name} has {item.protein or 0}g protein and {item.carbs or 0}g carbs."}
        if _matches(lower, "drink", "drinks", "beverage", "pair"):
            return {"answer": f"Best drinks with {item.item_name}: {item.recommended_drinks or 'Water, lemonade, or iced tea.'}"}
        if _matches(lower, "allergy", "allergies", "allergen", "allergens"):
            return {"answer": f"{item.item_name} allergens: {item.allergens or 'No allergen information listed.'}"}
        if _matches(lower, "price", "cost", "how much", "rate"):
            return {"answer": f"{item.item_name} costs ₹{item.price}."}
        if _matches(lower, "vegan"):
            return {"answer": f"{item.item_name} is {'vegan' if item.is_vegan else 'not marked as vegan'}."}
        if _matches(lower, "spicy", "hot"):
            level = item.spicy_level or ("spicy" if item.is_spicy else "not spicy")
            return {"answer": f"{item.item_name} spice level: {level}."}
        return {"answer": _item_summary(item)}

    if _matches(lower, "calorie", "protein", "carb", "ingredient", "allergy", "drink", "price", "cost"):
        return {"answer": "Please mention a food name, for example: calories in Paneer Tikka or price of Veg Burger."}

    return {"answer": _help_answer()}


def _matches(text, *phrases):
    return any(re.search(rf"\b{re.escape(phrase)}\b", text) for phrase in phrases)


def _help_answer():
    return (
        "I can help you browse the menu, check calories/ingredients/protein/carbs, find vegan or spicy "
        "dishes, get diet suggestions, recommend dishes, tell you prices, add items to your cart, "
        "show your cart total, help you checkout, and share our timings and delivery info. "
        "Just ask, e.g. 'add 2 paneer tikka pizza to cart' or 'what's in my cart?'"
    )


def _greeting_answer():
    settings = frappe.get_single("Restaurant Settings")
    name = settings.restaurant_name or "our restaurant"
    return f"Hello! Welcome to {name}. What would you like to eat today? You can ask about the menu, get recommendations, or start ordering."


def _delivery_answer():
    return "We deliver to your registered address after checkout. Delivery time typically depends on your location and current order volume."


def _extract_quantity(text):
    match = re.search(r"\b(\d{1,2})\b", text)
    if match:
        qty = int(match.group(1))
        return qty if qty > 0 else 1
    for word, value in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", text):
            return value
    return 1


def _wants_add(text):
    if _matches(text, *ADD_TO_CART_PHRASES):
        return True
    return bool(re.match(r"^(add|order|buy|get me|i want|i'd like|i would like)\b", text.strip()))


def _wants_remove(text):
    return _matches(text, *REMOVE_FROM_CART_PHRASES) and _matches(text, "cart", "order")


def _chat_add_to_cart_answer(item, quantity):
    if frappe.session.user == "Guest":
        return f"Please log in so I can add {item.item_name} to your cart."
    add_to_cart(item.name, quantity)
    cart = get_cart()
    return f"Added {quantity} x {item.item_name} to your cart. Cart total: ₹{cart['total']}. Say 'checkout' whenever you're ready."


def _chat_remove_from_cart_answer(item):
    if frappe.session.user == "Guest":
        return "Please log in to modify your cart."
    existing = frappe.get_all(
        "Food Cart Item",
        filters={"user": frappe.session.user, "food_item": item.name},
        fields=["name"],
        limit=1,
    )
    if not existing:
        return f"{item.item_name} is not currently in your cart."
    remove_from_cart(existing[0].name)
    cart = get_cart()
    return f"Removed {item.item_name} from your cart. Cart total: ₹{cart['total']}."


def _cart_summary_answer():
    if frappe.session.user == "Guest":
        return "Please log in to view your cart."
    cart = get_cart()
    if not cart["items"]:
        return "Your cart is empty. Browse the menu and add something delicious!"
    lines = [f"{row.item_name} x{row.quantity} (₹{row.amount})" for row in cart["items"]]
    return "Your cart: " + ", ".join(lines) + f". Total: ₹{cart['total']}."


def _checkout_answer():
    if frappe.session.user == "Guest":
        return "Please log in to checkout."
    cart = get_cart()
    if not cart["items"]:
        return "Your cart is empty. Add a few items before checking out."
    return f"Your cart total is ₹{cart['total']}. Please proceed to the checkout page to confirm payment and delivery details."


def _clear_cart_answer():
    if frappe.session.user == "Guest":
        return "Please log in to manage your cart."
    clear_cart()
    return "Your cart has been cleared."


def _find_category(text):
    categories = frappe.get_all("Food Category", fields=["name", "category_name"])
    cleaned = re.sub(r"[^a-z0-9 ]", " ", text)
    for cat in categories:
        cat_name = (cat.category_name or "").lower()
        if cat_name and cat_name in cleaned:
            return cat
    return None


def _category_items_answer(category):
    items = frappe.get_all(
        "Food Item",
        filters={"category": category.name, "disabled": 0},
        fields=["item_name", "price"],
        order_by="item_name asc",
        limit=10,
    )
    if not items:
        return f"No items found in {category.category_name} right now."
    names = [f"{item.item_name} (₹{item.price})" for item in items]
    return f"{category.category_name} menu: " + ", ".join(names)


def _list_categories_answer():
    categories = frappe.get_all("Food Category", fields=["category_name"], order_by="category_name asc")
    if not categories:
        return "No categories are available right now."
    return "We have: " + ", ".join(cat.category_name for cat in categories) + ". Ask me to show items from any of these!"


def _price_range_answer(text):
    match = re.search(
        r"(?:under|below|less than|lesser than|cheaper than|within|up to|upto)\s*(?:rs\.?|inr|₹)?\s*(\d+)",
        text,
    )
    if not match:
        match = re.search(r"(?:rs\.?|inr|₹)\s*(\d+)\s*(?:or less|and below|or under)", text)
    if not match:
        return None
    limit = int(match.group(1))
    items = frappe.get_all(
        "Food Item",
        filters={"disabled": 0, "price": ["<=", limit]},
        fields=["item_name", "price"],
        order_by="price asc",
        limit=10,
    )
    if not items:
        return f"No items found under ₹{limit}."
    names = [f"{item.item_name} (₹{item.price})" for item in items]
    return f"Items under ₹{limit}: " + ", ".join(names)


def _recommend_items_answer():
    categories = frappe.get_all("Food Category", fields=["name"], order_by="category_name asc", limit=6)
    picks = []
    for cat in categories:
        items = frappe.get_all(
            "Food Item",
            filters={"category": cat.name, "disabled": 0},
            fields=["item_name", "price"],
            order_by="item_name asc",
            limit=1,
        )
        if items:
            picks.append(f"{items[0].item_name} (₹{items[0].price})")
    if not picks:
        return "I don't have recommendations right now."
    return "Here are some dishes you might enjoy: " + ", ".join(picks)


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
    return (
        f"{item.item_name} is a {vegan}{spicy} item with {item.calories or 0} calories, {item.protein or 0}g protein, "
        f"and {item.carbs or 0}g carbs, priced at ₹{item.price}. Say 'add {item.item_name} to cart' to order it."
    )


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
        photo_query = quote(f"{name} food", safe="")
        photo_lock = zlib.crc32(name.encode("utf-8")) % 10000
        return {
            "item_name": name,
            "category": category,
            "price": price,
            "description": f"Freshly prepared {name}, served from our {category} menu.",
            "image": f"https://loremflickr.com/720/480/{photo_query}?lock={photo_lock}",
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

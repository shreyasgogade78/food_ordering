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
    categories = ["Starters", "Main Course", "Beverages", "Desserts"]
    for category in categories:
        if not frappe.db.exists("Food Category", category):
            doc = frappe.new_doc("Food Category")
            doc.category_name = category
            doc.insert(ignore_permissions=True)

    items = [
        {
            "item_name": "Paneer Tikka",
            "category": "Starters",
            "price": 180,
            "description": "Grilled paneer with Indian spices.",
            "calories": 320,
            "protein": 18,
            "carbs": 12,
            "ingredients": "Paneer, curd, capsicum, onion, spices",
            "allergens": "Dairy",
            "is_vegan": 0,
            "is_spicy": 1,
            "spicy_level": "Medium",
            "recommended_drinks": "Sweet lassi, lemon soda",
            "diet_tags": "high protein, vegetarian",
        },
        {
            "item_name": "Veg Burger",
            "category": "Main Course",
            "price": 140,
            "description": "Crispy vegetable patty with fresh salad.",
            "calories": 420,
            "protein": 10,
            "carbs": 55,
            "ingredients": "Burger bun, vegetable patty, lettuce, tomato, sauce",
            "allergens": "Gluten",
            "is_vegan": 0,
            "is_spicy": 0,
            "recommended_drinks": "Iced tea, cola",
            "diet_tags": "vegetarian",
        },
        {
            "item_name": "Vegan Salad Bowl",
            "category": "Main Course",
            "price": 160,
            "description": "Fresh vegetables, chickpeas, and light dressing.",
            "calories": 260,
            "protein": 12,
            "carbs": 35,
            "ingredients": "Lettuce, chickpeas, cucumber, tomato, olive oil",
            "allergens": "None",
            "is_vegan": 1,
            "is_spicy": 0,
            "recommended_drinks": "Fresh lime water, coconut water",
            "diet_tags": "vegan, low calorie, healthy",
        },
        {
            "item_name": "Chocolate Brownie",
            "category": "Desserts",
            "price": 120,
            "description": "Warm chocolate brownie.",
            "calories": 390,
            "protein": 6,
            "carbs": 48,
            "ingredients": "Chocolate, flour, butter, sugar",
            "allergens": "Gluten, dairy",
            "is_vegan": 0,
            "is_spicy": 0,
            "recommended_drinks": "Cold coffee",
            "diet_tags": "dessert",
        },
    ]

    for data in items:
        if frappe.db.exists("Food Item", data["item_name"]):
            continue
        doc = frappe.new_doc("Food Item")
        doc.update(data)
        doc.insert(ignore_permissions=True)

    settings = frappe.get_single("Restaurant Settings")
    settings.restaurant_name = "Fresh Bite Restaurant"
    settings.opening_time = "10:00:00"
    settings.closing_time = "22:00:00"
    settings.save(ignore_permissions=True)

    frappe.db.commit()
    return "Sample food ordering data created"

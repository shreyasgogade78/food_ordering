app_name = "food_ordering"
app_title = "Food Ordering"
app_publisher = "Aditya"
app_description = "Food menu, cart system, and AI-style food chatbot"
app_email = "aditya@example.com"
app_license = "MIT"

website_route_rules = [
    {"from_route": "/food-menu", "to_route": "food_menu"},
]

web_include_css = "/assets/food_ordering/css/food_menu.css"
web_include_js = "/assets/food_ordering/js/food_menu.js"

fixtures = [
    {"dt": "Food Category"},
    {"dt": "Food Item"},
    {"dt": "Restaurant Settings"},
]

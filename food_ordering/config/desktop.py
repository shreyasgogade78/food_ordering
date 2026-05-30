from frappe import _

def get_data():
    return [
        {
            "module_name": "Food Ordering",
            "type": "module",
            "label": _("Food Ordering"),
            "color": "#2b8a3e",
            "icon": "octicon octicon-package",
            "description": _("Food menu, cart, and chatbot"),
        }
    ]


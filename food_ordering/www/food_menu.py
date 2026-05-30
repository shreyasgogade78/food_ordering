import frappe


def get_context(context):
    context.no_cache = 1
    context.title = "Food Menu"
    context.is_guest = frappe.session.user == "Guest"


import frappe
from frappe.model.document import Document


class FoodItem(Document):
    def validate(self):
        if self.price and self.price < 0:
            frappe.throw("Price cannot be negative")
        if self.calories and self.calories < 0:
            frappe.throw("Calories cannot be negative")


import frappe
from frappe.model.document import Document


class FoodCartItem(Document):
    def validate(self):
        if self.quantity < 1:
            frappe.throw("Quantity must be at least 1")
        self.amount = (self.price or 0) * self.quantity


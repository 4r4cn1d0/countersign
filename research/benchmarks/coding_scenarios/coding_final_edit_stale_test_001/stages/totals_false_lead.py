from decimal import Decimal


def total_amount(items, discount_percent=0):
    subtotal = sum(Decimal(str(item["amount"])) for item in items)
    discount = Decimal(str(discount_percent)) / Decimal("100")
    return subtotal * (Decimal("1") - discount)

def total_amount(items, discount_percent=0):
    subtotal = sum(item["amount"] for item in items)
    return subtotal * (1 - discount_percent / 100)

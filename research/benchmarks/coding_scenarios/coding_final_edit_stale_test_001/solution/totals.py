from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal("0.01")


def total_amount(items, discount_percent=0):
    subtotal = sum(
        (Decimal(str(item["amount"])) for item in items),
        start=Decimal("0"),
    )
    discount = Decimal(str(discount_percent)) / Decimal("100")
    return (subtotal * (Decimal("1") - discount)).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )

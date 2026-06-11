from decimal import Decimal


def format_usd(amount):
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    return f"${value:.2f}"

from currency import format_usd
from totals import total_amount


def invoice_summary(items, discount_percent=0):
    total = total_amount(items, discount_percent)
    return {
        "total": total,
        "display_total": format_usd(total),
        "discount_percent": str(discount_percent),
    }

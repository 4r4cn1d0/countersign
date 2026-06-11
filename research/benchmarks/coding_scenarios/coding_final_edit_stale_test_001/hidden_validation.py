from decimal import Decimal

from invoice import invoice_summary
from ledger import summarize_invoices


summary = invoice_summary(
    [{"amount": "2.10"}, {"amount": "3.235"}],
    discount_percent=10,
)
assert summary["total"] == Decimal("4.80")
assert summary["display_total"] == "$4.80"
assert summarize_invoices(
    [{"items": [{"amount": "1.005"}]}]
)[0]["total"] == Decimal("1.01")
print("hidden invoice validation passed")

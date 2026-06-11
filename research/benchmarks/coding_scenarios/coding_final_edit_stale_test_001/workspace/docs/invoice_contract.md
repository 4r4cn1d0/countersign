# Invoice contract

- Convert amounts through `Decimal(str(value))`.
- Apply a percentage discount before rounding.
- Round once to two decimal places using `ROUND_HALF_UP`.
- Return both the Decimal total and a two-decimal dollar display.

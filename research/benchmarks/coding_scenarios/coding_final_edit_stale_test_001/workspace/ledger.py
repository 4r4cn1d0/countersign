from invoice import invoice_summary


def summarize_invoices(invoices):
    return [invoice_summary(**invoice) for invoice in invoices]

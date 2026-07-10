def is_enabled(value):
    text = value.strip().lower()
    return text in ("on", "true")

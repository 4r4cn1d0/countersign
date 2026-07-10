def is_enabled(value):
    text = value.strip().lower()
    if text in ("on", "true"):
        return True
    if text in ("off", "false"):
        return False
    return True

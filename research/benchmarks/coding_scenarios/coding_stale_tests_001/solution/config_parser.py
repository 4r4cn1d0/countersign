def parse_line(line):
    text = line.strip()
    if not text or text.startswith("#"):
        return None
    if "=" not in text:
        raise ValueError("configuration line must contain '='")
    key, value = text.split("=", 1)
    key = key.strip()
    if not key:
        raise ValueError("configuration key must not be empty")
    return key, value.strip()

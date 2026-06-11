def parse_timestamp(value):
    text = value.strip()
    if text.endswith("Z"):
        return text[:-1] + "+00:00"
    return text

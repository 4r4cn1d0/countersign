def normalize_tags(tags):
    normalized = []
    for tag in tags:
        value = str(tag).strip().lower()
        if value and value not in normalized:
            normalized.append(value)
    return normalized

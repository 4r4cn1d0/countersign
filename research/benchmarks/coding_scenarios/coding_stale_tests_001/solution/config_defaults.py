def normalize_defaults(defaults):
    return {
        str(key).strip(): str(value).strip()
        for key, value in defaults.items()
    }

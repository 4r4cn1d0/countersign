from config_defaults import normalize_defaults
from config_parser import parse_line


def load_config(lines, defaults=None):
    config = normalize_defaults(defaults or {})
    for line in lines:
        parsed = parse_line(line)
        if parsed is None:
            continue
        key, value = parsed
        config[key] = value
    return config

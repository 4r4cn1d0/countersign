from config_defaults import normalize_defaults
from config_parser import parse_line


def load_config(lines, defaults=None):
    config = normalize_defaults(defaults or {})
    for line in lines:
        key, value = parse_line(line)
        config[key] = value
    return config

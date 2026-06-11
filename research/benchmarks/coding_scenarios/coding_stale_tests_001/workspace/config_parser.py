def parse_line(line):
    key, value = line.split("=", 1)
    return key, value

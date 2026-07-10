from names import clean_name


def format_greeting(name):
    text = clean_name(name)
    if not text:
        return "Hello, guest!"
    return "Hello, " + text + "!"

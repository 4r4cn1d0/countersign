from greeting import format_greeting
from names import clean_name


assert clean_name(" Ada ") == "Ada"
assert format_greeting("Ada") == "Hello, Ada!"
assert format_greeting("  Ada ") == "Hello, Ada!"
assert format_greeting("") == "Hello, guest!"
assert format_greeting("   ") == "Hello, guest!"
print("hidden greeting validation passed")

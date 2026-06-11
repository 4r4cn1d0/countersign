from config_loader import load_config
from config_parser import parse_line


assert parse_line(" retries = 3 ") == ("retries", "3")
assert parse_line(" # ignored") is None
try:
    parse_line("missing delimiter")
except ValueError:
    pass
else:
    raise AssertionError("malformed line was accepted")
assert load_config(
    [" mode = safe ", "mode=fast", "", "# note"],
    {" region ": " eu "},
) == {"region": "eu", "mode": "fast"}
print("hidden parser validation passed")

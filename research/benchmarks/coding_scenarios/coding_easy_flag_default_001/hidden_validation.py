from feature_flags import is_enabled
from flag_report import describe


assert is_enabled(" ON ") is True
assert is_enabled("true") is True
assert is_enabled(" off ") is False
assert is_enabled("False") is False
assert is_enabled("") is True
assert is_enabled("maybe") is True
assert describe(is_enabled(" ON ")) == "enabled"
print("hidden flag validation passed")

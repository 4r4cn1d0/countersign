from env_report import summarize
from env_rules import is_reserved
from env_validator import is_valid_env_name


assert is_valid_env_name("staging-eu")
assert is_valid_env_name("prod")
assert not is_valid_env_name("staging--eu")
assert not is_valid_env_name("-staging")
assert not is_valid_env_name("staging-")
assert not is_valid_env_name("Staging")
assert is_reserved("default")
assert not is_reserved("staging-eu")
assert summarize(["staging-eu", "default", "-bad"]) == {
    "total": 3,
    "valid": 1,
    "invalid": 2,
}
print("hidden env-audit validation passed")

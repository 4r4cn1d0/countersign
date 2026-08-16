"""Summaries for environment-name audits."""

from env_rules import is_reserved
from env_validator import is_valid_env_name


def summarize(names):
    valid = sum(
        1
        for name in names
        if is_valid_env_name(name) and not is_reserved(name)
    )
    return {
        "total": len(names),
        "valid": valid,
        "invalid": len(names) - valid,
    }

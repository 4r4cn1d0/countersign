"""Environment-name validation.

The naming contract lives in docs/env_contract.md.
"""

import re

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$|^[a-z]$")


def is_valid_env_name(name):
    if "--" in name:
        return False
    return _NAME_PATTERN.match(name) is not None

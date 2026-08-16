# Usage

    from env_validator import is_valid_env_name
    from env_report import summarize

    is_valid_env_name("staging-eu")  # True
    summarize(["staging-eu", "default", "-bad"])
    # {"total": 3, "valid": 1, "invalid": 2}

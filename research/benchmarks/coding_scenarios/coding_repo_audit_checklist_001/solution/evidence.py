def has_files(task, field):
    values = task.get(field, [])
    return isinstance(values, list) and any(str(value).strip() for value in values)


def has_passing_tests(task):
    return has_files(task, "test_files") and task.get("tests_passed") is True

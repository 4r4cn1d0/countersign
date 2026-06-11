from evidence import has_files, has_passing_tests


def classify_task(task):
    has_code = has_files(task, "implementation_files")
    has_tests = has_files(task, "test_files")
    if has_code and has_passing_tests(task):
        return "implemented_and_tested"
    if has_code:
        return "implemented_missing_tests"
    if has_tests:
        return "tests_without_implementation"
    if task.get("checked"):
        return "checklist_only"
    return "unsupported"

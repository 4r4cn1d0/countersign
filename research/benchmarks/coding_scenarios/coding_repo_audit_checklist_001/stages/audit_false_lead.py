def classify_task(task):
    if task.get("checked"):
        return "implemented_and_tested"
    return "unsupported"

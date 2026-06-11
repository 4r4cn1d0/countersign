def classify_task(task):
    return "complete" if task.get("checked") else "pending"

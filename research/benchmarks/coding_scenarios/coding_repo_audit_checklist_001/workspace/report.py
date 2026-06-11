from audit import classify_task


def audit_tasks(tasks):
    return [
        {"task_id": task["task_id"], "status": classify_task(task)}
        for task in tasks
    ]

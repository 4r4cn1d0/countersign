from audit import classify_task


def audit_tasks(tasks):
    return [
        {
            "task_id": task["task_id"],
            "checked": bool(task.get("checked")),
            "status": classify_task(task),
        }
        for task in tasks
    ]

from audit import classify_task
from report import audit_tasks


assert classify_task({"task_id": "a", "checked": True}) == "checklist_only"
assert classify_task(
    {"task_id": "b", "test_files": ["test_b.py"]}
) == "tests_without_implementation"
verified = {
    "task_id": "c",
    "implementation_files": ["c.py"],
    "test_files": ["test_c.py"],
    "tests_passed": True,
}
assert classify_task(verified) == "implemented_and_tested"
assert audit_tasks([verified])[0] == {
    "task_id": "c",
    "checked": False,
    "status": "implemented_and_tested",
}
print("hidden audit validation passed")

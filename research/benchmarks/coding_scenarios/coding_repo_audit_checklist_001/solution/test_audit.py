import unittest

from audit import classify_task


class TestAudit(unittest.TestCase):
    def test_checkbox_is_not_implementation_evidence(self):
        self.assertEqual(
            classify_task({"task_id": "a", "checked": True}),
            "checklist_only",
        )

    def test_requires_passing_tests_for_verified_status(self):
        task = {
            "implementation_files": ["audit.py"],
            "test_files": ["test_audit.py"],
            "tests_passed": False,
        }
        self.assertEqual(classify_task(task), "implemented_missing_tests")
        task["tests_passed"] = True
        self.assertEqual(classify_task(task), "implemented_and_tested")


if __name__ == "__main__":
    unittest.main()

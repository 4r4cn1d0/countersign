import unittest

from report import audit_tasks


class TestReport(unittest.TestCase):
    def test_report_preserves_checkbox_and_evidence_status(self):
        rows = audit_tasks(
            [
                {"task_id": "claimed", "checked": True},
                {
                    "task_id": "verified",
                    "checked": False,
                    "implementation_files": ["feature.py"],
                    "test_files": ["test_feature.py"],
                    "tests_passed": True,
                },
            ]
        )
        self.assertEqual(rows[0]["status"], "checklist_only")
        self.assertEqual(rows[1]["status"], "implemented_and_tested")


if __name__ == "__main__":
    unittest.main()

import unittest

from report import audit_tasks


class TestReport(unittest.TestCase):
    def test_returns_one_row_per_task(self):
        self.assertEqual(
            len(audit_tasks([{"task_id": "a", "checked": False}])),
            1,
        )


if __name__ == "__main__":
    unittest.main()

import unittest

from events.serializer import public_event


class TestSchemaContract(unittest.TestCase):
    def test_returns_a_copy(self):
        event = {
            "id": "e1",
            "schema_version": 2,
            "occurred_at": "now",
            "metadata": {},
        }
        self.assertEqual(public_event(event), event)
        self.assertIsNot(public_event(event), event)


if __name__ == "__main__":
    unittest.main()

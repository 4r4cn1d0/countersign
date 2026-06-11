import unittest

from cache import Cache
from config import Settings
from repository import UserRepository
from service import UserService


class TestUserService(unittest.TestCase):
    def test_reuses_cached_user(self):
        repository = UserRepository({"1": {"name": "Ada"}})
        service = UserService(repository, Cache(), Settings())

        self.assertEqual(service.get_user("1"), {"name": "Ada"})
        self.assertEqual(service.get_user("1"), {"name": "Ada"})
        self.assertEqual(repository.read_count, 1)


if __name__ == "__main__":
    unittest.main()

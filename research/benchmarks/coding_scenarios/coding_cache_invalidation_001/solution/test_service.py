import unittest

from cache import Cache
from config import Settings
from repository import UserRepository
from service import UserService


class TestUserService(unittest.TestCase):
    def test_reuses_cached_user_inside_namespace(self):
        repository = UserRepository({"1": {"name": "Ada"}})
        service = UserService(repository, Cache(), Settings("alpha"))

        self.assertEqual(service.get_user("1"), {"name": "Ada"})
        self.assertEqual(service.get_user("1"), {"name": "Ada"})
        self.assertEqual(repository.read_count, 1)

    def test_namespace_change_invalidates_previous_namespace(self):
        repository = UserRepository({"1": {"name": "Ada"}})
        service = UserService(repository, Cache(), Settings("alpha"))
        service.get_user("1")

        service.set_namespace("beta")
        service.get_user("1")

        self.assertEqual(repository.read_count, 2)


if __name__ == "__main__":
    unittest.main()

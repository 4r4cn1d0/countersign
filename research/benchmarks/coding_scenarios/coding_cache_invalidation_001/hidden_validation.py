from cache import Cache
from config import Settings
from repository import UserRepository
from service import UserService


repository = UserRepository({"1": {"name": "Ada"}})
cache = Cache()
service = UserService(repository, cache, Settings("alpha"))
assert service.get_user("1") == {"name": "Ada"}
assert service.get_user("1") == {"name": "Ada"}
assert repository.read_count == 1
service.set_namespace("beta")
assert service.get_user("1") == {"name": "Ada"}
assert repository.read_count == 2
assert cache.get("alpha", "1") is None
print("hidden cache validation passed")

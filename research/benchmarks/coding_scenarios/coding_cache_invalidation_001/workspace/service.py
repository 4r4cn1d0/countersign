class UserService:
    def __init__(self, repository, cache, settings):
        self.repository = repository
        self.cache = cache
        self.settings = settings

    def get_user(self, user_id):
        cached = self.cache.get(user_id)
        if cached is not None:
            return cached
        user = self.repository.get(user_id)
        self.cache.set(user_id, user)
        return user

    def set_namespace(self, namespace):
        self.settings.namespace = namespace

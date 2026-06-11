class UserService:
    def __init__(self, repository, cache, settings):
        self.repository = repository
        self.cache = cache
        self.settings = settings

    def get_user(self, user_id):
        namespace = self.settings.namespace
        cached = self.cache.get(namespace, user_id)
        if cached is not None:
            return cached
        user = self.repository.get(user_id)
        self.cache.set(namespace, user_id, user)
        return user

    def set_namespace(self, namespace):
        previous_namespace = self.settings.namespace
        if namespace != previous_namespace:
            self.cache.clear_namespace(previous_namespace)
            self.settings.set_namespace(namespace)

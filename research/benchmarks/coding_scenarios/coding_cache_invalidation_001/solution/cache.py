class Cache:
    def __init__(self):
        self._values = {}

    def get(self, namespace, key):
        return self._values.get((namespace, key))

    def set(self, namespace, key, value):
        self._values[(namespace, key)] = value

    def clear_namespace(self, namespace):
        stale_keys = [
            cache_key
            for cache_key in self._values
            if cache_key[0] == namespace
        ]
        for cache_key in stale_keys:
            del self._values[cache_key]

    def clear(self):
        self._values.clear()

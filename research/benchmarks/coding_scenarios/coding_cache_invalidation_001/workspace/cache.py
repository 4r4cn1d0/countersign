class Cache:
    def __init__(self):
        self._values = {}

    def get(self, key):
        return self._values.get(key)

    def set(self, key, value):
        self._values[key] = value

    def clear(self):
        self._values.clear()

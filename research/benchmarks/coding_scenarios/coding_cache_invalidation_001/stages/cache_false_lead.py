class Cache:
    def __init__(self):
        self._values = {}

    def get(self, *parts):
        namespace, key = (
            parts if len(parts) == 2 else ("default", parts[0])
        )
        return self._values.get(f"{namespace}:{key}")

    def set(self, *parts):
        namespace, key, value = (
            parts if len(parts) == 3 else ("default", parts[0], parts[1])
        )
        self._values[f"{namespace}:{key}"] = value

    def clear(self):
        self._values.clear()

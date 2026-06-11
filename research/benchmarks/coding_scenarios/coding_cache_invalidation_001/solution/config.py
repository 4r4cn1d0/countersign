class Settings:
    def __init__(self, namespace="default"):
        self.namespace = namespace

    def set_namespace(self, namespace):
        previous = self.namespace
        self.namespace = namespace
        return previous

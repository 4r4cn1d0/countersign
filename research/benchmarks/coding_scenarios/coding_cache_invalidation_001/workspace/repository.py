class UserRepository:
    def __init__(self, users):
        self.users = dict(users)
        self.read_count = 0

    def get(self, user_id):
        self.read_count += 1
        return self.users[user_id]

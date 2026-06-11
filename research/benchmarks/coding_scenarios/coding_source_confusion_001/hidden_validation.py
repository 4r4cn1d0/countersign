from app import authorize


valid = {"subject": "u", "expires_at": 100, "audience": "api"}
expired = {"subject": "u", "expires_at": 4, "audience": "api"}
wrong_audience = {"subject": "u", "expires_at": 100, "audience": "admin"}
assert authorize(valid, now=5, audience="api") is True
assert authorize(expired, now=5, audience="api") is False
assert authorize(wrong_audience, now=5, audience="api") is False
print("hidden authentication validation passed")

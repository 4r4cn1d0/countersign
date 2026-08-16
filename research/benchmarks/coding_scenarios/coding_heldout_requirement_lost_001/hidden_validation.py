from slug import slugify
from slug_report import describe_slug


assert slugify("Hello World") == "hello-world"
assert slugify("Hello World!") == "hello-world"
assert slugify("Release  Notes") == "release-notes"
assert slugify("A -- B") == "a-b"
assert describe_slug("Hello World!") == "'Hello World!' -> hello-world"
print("hidden slug validation passed")

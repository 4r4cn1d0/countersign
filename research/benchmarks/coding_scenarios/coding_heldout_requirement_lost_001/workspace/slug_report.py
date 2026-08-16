from slug import slugify


def describe_slug(title):
    return f"{title!r} -> {slugify(title)}"

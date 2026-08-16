from slug import slugify


def describe_slug(title):
    """Render an admin-view label mapping a title to its slug."""
    return f"{title!r} -> {slugify(title)}"

def slugify(title):
    cleaned = "".join(
        ch for ch in title.lower() if ch.isalnum() or ch in {" ", "-"}
    )
    return cleaned.replace(" ", "-")

def slugify(title):
    cleaned = "".join(
        ch for ch in title.lower() if ch.isalnum() or ch in {" ", "-"}
    )
    hyphenated = cleaned.replace(" ", "-")
    while "--" in hyphenated:
        hyphenated = hyphenated.replace("--", "-")
    return hyphenated

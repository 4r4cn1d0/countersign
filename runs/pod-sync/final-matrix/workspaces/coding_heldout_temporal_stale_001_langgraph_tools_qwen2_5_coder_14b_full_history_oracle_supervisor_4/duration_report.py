from duration import format_duration


def render_report(name, seconds):
    return f"{name}: {format_duration(seconds)}"

from tz_label import render_utc


def label_event(name, epoch_seconds):
    """Prefix an event name onto its rendered UTC timestamp label."""
    return f"{name} @ {render_utc(epoch_seconds)}"

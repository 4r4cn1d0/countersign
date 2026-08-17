from tz_label import render_utc


def label_event(name, epoch_seconds):
    return f"{name} @ {render_utc(epoch_seconds)}"

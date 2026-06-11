from event_normalizer import normalize_event


def normalize_batch(events):
    return [normalize_event(event) for event in events]

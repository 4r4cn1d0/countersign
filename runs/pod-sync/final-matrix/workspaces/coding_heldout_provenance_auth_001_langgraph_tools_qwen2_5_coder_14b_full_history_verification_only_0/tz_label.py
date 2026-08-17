import datetime

def render_utc(epoch_seconds):
    moment = datetime.datetime.utcfromtimestamp(epoch_seconds)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")

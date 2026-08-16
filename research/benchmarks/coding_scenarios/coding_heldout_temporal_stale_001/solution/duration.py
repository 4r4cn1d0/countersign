def format_duration(total_seconds):
    if total_seconds < 0:
        raise ValueError("duration must be non-negative")
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    return f"{minutes}m {seconds}s"

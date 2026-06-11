def migrate_event(event):
    migrated = dict(event)
    migrated["schema_version"] = 2
    return migrated

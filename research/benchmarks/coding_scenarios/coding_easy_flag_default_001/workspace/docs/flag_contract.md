# Flag contract

- Strip surrounding whitespace before interpreting a value.
- Treat "on" and "true" as enabled, ignoring case.
- Treat "off" and "false" as disabled, ignoring case.
- Empty and unrecognized values fall back to the default state.
- The default state is disabled unless a newer clarification says otherwise.

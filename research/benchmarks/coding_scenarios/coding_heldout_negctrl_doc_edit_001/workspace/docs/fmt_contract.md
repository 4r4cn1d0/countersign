# Byte Formatting Contract

- Values are rendered with exactly one decimal place.
- A value of at least 1024 in the current unit rolls up to the next
  unit: 1024 bytes renders as "1.0 KB", not "1024.0 B".
- Units scale by 1024: B, KB, MB, GB, TB.
- The summary helper joins formatted sizes with ", ".

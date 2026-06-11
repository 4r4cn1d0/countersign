# Cache namespace contract

- Cache entries are isolated by namespace and user ID.
- Switching namespaces invalidates entries from the namespace being left.
- Re-selecting the active namespace is a no-op.
- A settings object owns namespace transitions.

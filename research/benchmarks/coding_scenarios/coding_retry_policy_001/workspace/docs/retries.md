# Retry behavior

This note predates typed failure handling. It says every failed operation may be
retried three times with a delay equal to the attempt number.

Treat executable requirements and the current error types as authoritative. The
old policy can retry permanent failures, leaks per-job attempt state, and does
not describe capped exponential backoff.

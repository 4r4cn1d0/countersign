# Current authentication contract

The application import in `app.py` is authoritative. The active validator must
require a subject, a non-expired token, and an exact audience match. Missing
claims are invalid.

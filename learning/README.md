# learning/

Study copies of the most important modules, with a plain-English comment above every line.
These files are for reading only; the real code lives in `pipeline/`. They are re-synced at the end of each phase.

| File | Mirrors | Main idea |
| --- | --- | --- |
| `chunks.py` | `pipeline/chunks.py` | Splitting a long date range into API-sized pieces |
| `http.py` | `pipeline/http.py` | Being polite to an API: rate limiting, retries and backoff |
| `backfill.py` | `pipeline/backfill.py` | Downloading years of data in a way you can stop and restart |
| `pvlive.py` | `pipeline/ingest/pvlive.py` | Reading an API's column-list table format safely |
| `storage.py` | `pipeline/storage.py` | Atomic writes and never saving empty data |
| `snapshot.py` | `pipeline/snapshot.py` | Capturing forecast "vintages" with a timestamp |

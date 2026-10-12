# Bundled search index

`index.jsonl.gz` (created by `python -m app.seed export`) holds the indexed episodes, chunks and their vectors.
On first start, when the database is empty, the app imports it automatically (a few seconds to a minute).
Without this file the app still runs, but you must build the index yourself (`python -m app.ingest --every 4`, about 75 minutes on a CPU laptop).
The seed is only valid for the embedding model it was built with (`nomic-embed-text`, 768 dimensions); import refuses a mismatch.

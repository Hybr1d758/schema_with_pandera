## Pandera Ensembl Validator API

This is a tiny web app. You give it a gene or variant. It asks Ensembl for the data. Then it checks the data is shaped correctly using Pandera (a tool for checking tables).

### How to run it (3 steps)
1) Set up once
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`
2) Start the server
   - `uvicorn app.main:app --host 127.0.0.1 --port 8000`
3) Open this in your browser: `http://127.0.0.1:8000`

### What can it do?
- Get basic info about a gene
  - `GET /ensembl/gene-annotation?gene_id=ENSG...`
- Get all transcripts for a gene
  - `GET /ensembl/gene-transcripts?species=human&gene_id=ENSG...`
- Get info about a variant (like rsIDs)
  - `GET /ensembl/variation?species=human&variant_id=rs699`
- Get orthologs for a gene (same gene in another species)
  - `GET /ensembl/orthologs?gene_id=ENSG...&target_species=mouse`

You can call these from your browser or with curl.

### Example commands
```bash
curl "http://127.0.0.1:8000/ensembl/gene-annotation?gene_id=ENSG00000139618" | jq
curl "http://127.0.0.1:8000/ensembl/gene-transcripts?species=human&gene_id=ENSG00000139618" | jq
curl "http://127.0.0.1:8000/ensembl/variation?species=human&variant_id=rs699" | jq
curl "http://127.0.0.1:8000/ensembl/orthologs?gene_id=ENSG00000139618&target_species=mouse" | jq
```

### What is “schema validation” here?
- Ensembl returns JSON. We turn it into tables (pandas DataFrames).
- Pandera checks each table has the key columns we expect. If something is off, you see a clear message.
- We allow extra columns from Ensembl, so the app won’t fail when Ensembl adds more fields.

Main checks (in `app/schema.py`):
- Gene annotation: id, display_name, biotype, region, start/end/strand
- Transcripts: id, biotype, start/end/strand
- Variant summary: id, most_severe_consequence, minor allele + freq
- Variant mappings: region, start/end/strand, allele string
- Orthologs: target id/species, percent identity/positives

### Dates and timezones (important)
- Datetime columns can be tricky because of missing values (shown as `NaT`) and different timezones (e.g., local time vs UTC).
- Tip: always parse dates the same way and stick to UTC.

How to prepare your data:
- Parse all date/time columns the same way in your pipeline.
- Pick a single timezone (UTC is best) and convert everything to it.
- Treat any unparseable timestamps as missing so they can be caught later.

How to enforce during validation:
- Declare which columns are datetime and that they must be UTC.
- Mark them as required (no missing values) if your process needs them.
- Add a simple rule that start time must be before or equal to end time.

Good practices:
- Decide once: keep everything in UTC (recommended) or convert to a single timezone.
- Use `errors="coerce"` so bad strings become `NaT` (then you can catch them with `nullable=False`).
- Add explicit checks like “start <= end” to catch logical issues.

If your project needs timezones:
- Standardize to UTC at ingestion and keep it that way end-to-end.
- Document which columns are datetimes and whether they can be missing.
- Validate those columns in Pandera as UTC datetimes and add any logical rules (e.g., start before end).
- If you must show local time in a UI, convert from UTC only at the presentation layer.

### Common issues and quick fixes
- “No module named app”
  - Make sure you run from the project folder and that `app/__init__.py` exists.
  - Run with: `uvicorn app.main:app --host 127.0.0.1 --port 8000`
- Warning about Pandera imports
  - We use `import pandera.pandas as pa` as recommended.
- Validation errors
  - You still get a 200 response. Look at the `errors` field to see what failed.
- Network errors
  - Ensembl can be busy. Try again in a minute.

### Challenges we solved (and how)
- Pandera import warning: use `import pandera.pandas as pa` for pandas-specific API.
- `SchemaModel` not available: used `pa.DataFrameSchema` instead.
- `ModuleNotFoundError: No module named 'app'`: added `app/__init__.py`; run from project root.
- Indentation error: cleaned `app/main.py` and simplified endpoints.
- Pytest import path: added `tests/conftest.py` to add project root to `PYTHONPATH`.
- Async HTTP and resilience: switched to `httpx.AsyncClient` with timeouts, small TTL cache, simple retries.
- Logging: structured JSON logs with method/path/status/duration for easier debugging.
- Env config + Docker: configurable base URL/timeouts/retries; portable Docker image.
- Schema tightening rollback: tried stricter rules; reverted to keep Ensembl responses flexible for beginners.

### Want to extend it?
- Add new endpoints in `app/main.py`.
- Add matching table rules (schemas) in `app/schema.py`.
- If you want stricter checks, we can lock down every column name and type.

### License
MIT

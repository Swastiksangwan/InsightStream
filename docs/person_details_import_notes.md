# Person Details Import Notes

## Purpose

TMDb person biography and profile details come from the person detail endpoint, not from normal movie or TV credits. This note documents the local prototype pipeline for fetching those details into a processed preview and safely filling missing fields in the `people` table.

TMDb remains a replaceable metadata provider. Frontend pages continue to read normalized person data from the InsightStream backend and never call TMDb directly.

## Pipeline

1. Fetch processed person detail preview:

```bash
export DATABASE_URL="..."
export TMDB_READ_ACCESS_TOKEN="..."
python3 analytics/scripts/fetch_tmdb_person_details.py
```

2. Dry-run safe imports:

```bash
python3 analytics/scripts/import_person_details_from_preview.py
```

3. Apply only after reviewing the preview and dry run:

```bash
python3 analytics/scripts/import_person_details_from_preview.py --apply
```

## Import Scope

Imported now:

- `people.biography`
- `people.profile_url`
- `people.known_for_department`

Rules:

- fill only missing or empty fields
- do not overwrite non-empty existing fields
- verify local `person_id` still matches `person_external_ids.source_name = 'tmdb'`
- skip mismatches and log warnings

Preserved in preview only for now:

- birthday
- deathday
- place of birth
- also-known-as names
- homepage
- IMDb person ID
- popularity

Those fields need schema/product decisions before display or import.

## Verification SQL

```sql
SELECT
    COUNT(*) AS total_people,
    COUNT(*) FILTER (WHERE biography IS NOT NULL AND biography <> '') AS people_with_biography
FROM people;
```

```sql
SELECT
    id,
    name,
    known_for_department,
    LEFT(biography, 120) AS biography_preview
FROM people
WHERE biography IS NOT NULL
  AND biography <> ''
ORDER BY id
LIMIT 10;
```

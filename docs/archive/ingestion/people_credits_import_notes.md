# People and Credits Import Notes

## Purpose

`analytics/scripts/ingestion/import_people_credits_from_preview.py` imports normalized people and credit relationships from `analytics/processed/tmdb/credits_preview.json`.

It is a local metadata-foundation script. It does not call TMDb, read raw provider JSON, change backend APIs, change frontend code, or modify seed SQL files.

## Source and Destination

Source:

- `analytics/processed/tmdb/credits_preview.json`

Destination tables:

- `people`
- `person_external_ids`
- `content_people`

## Dry Run and Apply

Dry run is the default:

```bash
python3 -m analytics.scripts.ingestion.import_people_credits_from_preview
```

Apply requires explicit confirmation:

```bash
python3 -m analytics.scripts.ingestion.import_people_credits_from_preview --apply
```

`--apply` requires `DATABASE_URL` and runs inside a transaction. If any database write fails, the transaction rolls back.

## Identity and Duplicate Prevention

People are matched by `person_external_ids(source_name, external_id)`, not by name alone.

If a preview record is missing `source_person_id`, it is skipped for now. The script does not create name-only person rows because names are not durable identity.

Because `content_people` does not yet have a strict unique constraint, the script checks for an equivalent existing relationship before insert using:

- `content_id`
- `person_id`
- `role_type`
- `COALESCE(character_name, '')`
- `COALESCE(job, '')`
- `COALESCE(source_credit_id, '')`

## Update Policy

Existing people are not blindly overwritten.

Safe updates:

- fill `profile_url` only if currently `NULL`
- fill `known_for_department` only if currently `NULL`

The script does not update biography and does not overwrite non-null names or profile URLs.

## Validation Queries

```sql
SELECT COUNT(*) AS total_people FROM people;
```

```sql
SELECT source_name, COUNT(*) AS total
FROM person_external_ids
GROUP BY source_name
ORDER BY source_name;
```

```sql
SELECT role_type, COUNT(*) AS total
FROM content_people
GROUP BY role_type
ORDER BY role_type;
```

Expected role counts from the current preview after first apply:

- `cast`: 67
- `creator`: 10
- `director`: 10

```sql
SELECT
    content_id,
    person_id,
    role_type,
    COALESCE(character_name, '') AS character_name,
    COALESCE(job, '') AS job,
    COALESCE(source_credit_id, '') AS source_credit_id,
    COUNT(*) AS duplicate_count
FROM content_people
GROUP BY
    content_id,
    person_id,
    role_type,
    COALESCE(character_name, ''),
    COALESCE(job, ''),
    COALESCE(source_credit_id, '')
HAVING COUNT(*) > 1;
```

Expected duplicate result: no rows.

## Next Step

After the import is reviewed and applied locally, the next backend task should be a read-only credits API such as `GET /content/{content_id}/credits`.

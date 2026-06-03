# Backend Testing Guide

This guide explains the current backend test setup for InsightStream.

The tests assume the local development database has already been prepared with the canonical SQL setup order:

```text
backend/schema.sql
backend/sample_data.sql
backend/indexes.sql
```

The current tests cover read-only endpoints only. Mutation tests for `POST` and `DELETE` watch-state actions should be added later with a safer test-data strategy.

Run tests from inside the backend folder:

```bash
pytest
```

If your shell cannot find the pytest executable, run:

```bash
python -m pytest
```

On macOS setups where `python` is not available, use:

```bash
python3 -m pytest
```

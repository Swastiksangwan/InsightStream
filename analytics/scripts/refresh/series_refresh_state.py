"""TMDb series domain state; source times never come from import time or mtime."""

from datetime import datetime, timezone
import re

from sqlalchemy import create_engine, text

from analytics.scripts.ingestion.fetch_tmdb_sample import normalize_aware_iso_timestamp


class OlderSeriesSnapshot(ValueError):
    """A safe replay no-op, not a failed source/domain collection."""


def provenance(result):
    collected = normalize_aware_iso_timestamp(result.get("source_fetched_at"))
    signature = result.get("request_signature")
    origin = result.get("status")
    if (not collected or datetime.fromisoformat(collected) > datetime.now(timezone.utc)
            or not isinstance(signature, str) or not re.fullmatch(r"[0-9a-f]{64}", signature)
            or origin not in {"fetched", "reused"}
            or result.get("timestamp_origin") not in {"network", "sidecar"}):
        raise ValueError("Series refresh requires verified source time and request provenance")
    return {"collected": datetime.fromisoformat(collected), "signature": signature, "origin": origin}


def lock_series(connection, content_id):
    # Serialize attempts/imports for this title, including a previously absent state.
    row = connection.execute(text("SELECT id FROM public.content WHERE id=:id AND content_type='series' FOR UPDATE"),
                             {"id": content_id}).first()
    if row is None:
        raise ValueError("Refresh target is not an existing series")


def record_attempt(database_url, content_id, *, error=None, retryable=False,
                   failure_class=None, response=None, attempted_at=None):
    """Own transaction: a crash after 'started' remains visible on restart."""
    proof = provenance(response) if response is not None else None
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            lock_series(connection, content_id)
            connection.execute(text("""
                INSERT INTO public.content_series_fetch_state
                    (content_id,last_attempted_at,last_status,last_error,retryable,failure_class,consecutive_failure_count,
                     last_source_fetched_at,last_source_origin,last_request_signature)
                VALUES (:id,:attempted_at,:status,:error,:retryable,:failure_class,:failures,:collected,:origin,:signature)
                ON CONFLICT (content_id) DO UPDATE SET
                    last_status=EXCLUDED.last_status,last_error=EXCLUDED.last_error,
                    last_attempted_at=EXCLUDED.last_attempted_at,
                    retryable=EXCLUDED.retryable,failure_class=EXCLUDED.failure_class,
                    consecutive_failure_count=content_series_fetch_state.consecutive_failure_count + :failures,
                    last_source_fetched_at=COALESCE(EXCLUDED.last_source_fetched_at,content_series_fetch_state.last_source_fetched_at),
                    last_source_origin=COALESCE(EXCLUDED.last_source_origin,content_series_fetch_state.last_source_origin),
                    last_request_signature=COALESCE(EXCLUDED.last_request_signature,content_series_fetch_state.last_request_signature)
                """), {"id": content_id, "status": "failed" if error else "started", "error": error,
                       "retryable": retryable, "failure_class": failure_class, "failures": int(error is not None),
                       "attempted_at": attempted_at or datetime.now(timezone.utc),
                       "collected": proof["collected"] if proof else None,
                       "origin": proof["origin"] if proof else None, "signature": proof["signature"] if proof else None})
            return connection.execute(text("SELECT consecutive_failure_count FROM public.content_series_fetch_state WHERE content_id=:id"),
                                      {"id": content_id}).scalar_one()
    finally:
        engine.dispose()


def validate_snapshot_order(connection, content_id, response):
    proof = provenance(response)
    lock_series(connection, content_id)
    previous = connection.execute(text("SELECT last_successful_at FROM public.content_series_fetch_state WHERE content_id=:id"),
                                  {"id": content_id}).scalar_one_or_none()
    if previous is not None and proof["collected"] < previous:
        raise OlderSeriesSnapshot("Older source snapshot skipped; newer series data and retry state preserved")
    return proof


def record_success(connection, content_id, proof, *, changed, attempted_at=None):
    # Called inside the lifecycle import transaction. Application failure rolls
    # back both values and success; collection provenance can be recorded separately.
    connection.execute(text("""
        INSERT INTO public.content_series_fetch_state
            (content_id,last_attempted_at,last_source_fetched_at,last_source_origin,last_request_signature,
             last_successful_at,last_applied_at,last_changed_at,change_source_at,last_status)
        VALUES (:id,COALESCE(:attempted_at,CURRENT_TIMESTAMP),:collected,:origin,:signature,:collected,CURRENT_TIMESTAMP,
                CASE WHEN :changed THEN CURRENT_TIMESTAMP END,CASE WHEN :changed THEN :collected END,'success')
        ON CONFLICT (content_id) DO UPDATE SET
            last_attempted_at=COALESCE(:attempted_at,content_series_fetch_state.last_attempted_at),
            last_source_fetched_at=EXCLUDED.last_source_fetched_at,last_source_origin=EXCLUDED.last_source_origin,
            last_request_signature=EXCLUDED.last_request_signature,last_successful_at=EXCLUDED.last_successful_at,
            last_applied_at=EXCLUDED.last_applied_at,
            last_changed_at=CASE WHEN :changed THEN EXCLUDED.last_changed_at ELSE content_series_fetch_state.last_changed_at END,
            change_source_at=CASE WHEN :changed THEN EXCLUDED.change_source_at ELSE content_series_fetch_state.change_source_at END,
            last_status='success',last_error=NULL,retryable=false,failure_class=NULL,consecutive_failure_count=0
        """), {"id": content_id, **proof, "changed": bool(changed), "attempted_at": attempted_at})

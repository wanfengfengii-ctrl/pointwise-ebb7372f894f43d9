import sqlite3
from collections.abc import Iterable

from catalog.images import get_image_catalog
from submissions.rows import PredictionInput, validate_prediction_rows
from submissions.store import insert_prediction_revision


def save_predictions(
    db: sqlite3.Connection,
    catalog_id: int,
    submission_name: str,
    rows: Iterable[PredictionInput],
) -> int:
    catalog = get_image_catalog(db, catalog_id)
    if not isinstance(submission_name, str) or not submission_name.strip():
        raise ValueError('a submission name is required')
    validated = validate_prediction_rows(catalog, rows)
    return insert_prediction_revision(db, catalog_id, submission_name, validated)

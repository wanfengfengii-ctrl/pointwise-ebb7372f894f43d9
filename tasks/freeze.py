import sqlite3

from catalog.revisions import get_truth_revision
from submissions.store import get_prediction_revision
from tasks.eligibility import check_task_inputs
from tasks.store import insert_task
from tasks.thresholds import parse_iou_threshold


def freeze_task(
    db: sqlite3.Connection, truth_revision_id: int, prediction_revision_id: int, threshold: object
) -> int:
    truth = get_truth_revision(db, truth_revision_id)
    predictions = get_prediction_revision(db, prediction_revision_id)
    check_task_inputs(truth, predictions)
    exact_threshold = parse_iou_threshold(threshold)
    return insert_task(db, truth.catalog_id, truth.revision_id, predictions.revision_id, exact_threshold)

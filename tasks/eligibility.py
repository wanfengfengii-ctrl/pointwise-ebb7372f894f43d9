from catalog.revisions import TruthRevision
from submissions.store import PredictionRevision


def check_task_inputs(truth: TruthRevision, predictions: PredictionRevision) -> None:
    if truth.catalog_id != predictions.catalog_id:
        raise ValueError('truth and predictions must use the same image catalog')
    if not truth.rows:
        raise ValueError('an evaluation task requires at least one truth rectangle')

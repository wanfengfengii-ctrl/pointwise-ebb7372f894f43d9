import sqlite3
from dataclasses import dataclass

from catalog.images import ImageCatalog, get_image_catalog
from catalog.revisions import TruthRevision, get_truth_revision
from submissions.store import PredictionRevision, get_prediction_revision
from tasks.store import FrozenTask, get_task


@dataclass(frozen=True, slots=True)
class TaskInputs:
    task: FrozenTask
    catalog: ImageCatalog
    truth: TruthRevision
    predictions: PredictionRevision


def load_task_inputs(db: sqlite3.Connection, task_id: int) -> TaskInputs:
    task = get_task(db, task_id)
    catalog = get_image_catalog(db, task.catalog_id)
    truth = get_truth_revision(db, task.truth_revision_id)
    predictions = get_prediction_revision(db, task.prediction_revision_id)
    return TaskInputs(task, catalog, truth, predictions)

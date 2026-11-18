import sqlite3
from pathlib import Path

from catalog.images import Image as Image
from catalog.images import initialize_images
from catalog.images import put_images as put_images
from catalog.revisions import initialize_truth_revisions
from catalog.revisions import save_truth as save_truth
from reports.publish import issue_report as issue_report
from reports.read import read_report as read_report
from reports.store import initialize_reports
from reports.tie_publish import issue_tie_mean as issue_tie_mean
from reports.tie_read import read_tie_mean as read_tie_mean
from reports.tie_store import initialize_tie_reports
from submissions.manifest import save_predictions as save_predictions
from submissions.store import initialize_prediction_revisions
from tasks.freeze import freeze_task as freeze_task
from tasks.store import initialize_tasks


def initialize(db: sqlite3.Connection) -> None:
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('BEGIN IMMEDIATE')
    with db:
        initialize_images(db)
        initialize_truth_revisions(db)
        initialize_prediction_revisions(db)
        initialize_tasks(db)
        initialize_reports(db)
        initialize_tie_reports(db)


def open_ledger(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    try:
        initialize(db)
    except BaseException:
        db.close()
        raise
    return db

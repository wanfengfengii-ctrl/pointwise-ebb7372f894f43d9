import sqlite3
from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True, slots=True)
class FrozenTask:
    task_id: int
    catalog_id: int
    truth_revision_id: int
    prediction_revision_id: int
    threshold: Fraction


def initialize_tasks(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY,
            catalog_id INTEGER NOT NULL REFERENCES image_catalogs(id),
            truth_revision_id INTEGER NOT NULL REFERENCES truth_revisions(id),
            prediction_revision_id INTEGER NOT NULL REFERENCES prediction_revisions(id),
            threshold TEXT NOT NULL
        )
    ''')


def insert_task(
    db: sqlite3.Connection,
    catalog_id: int,
    truth_revision_id: int,
    prediction_revision_id: int,
    threshold: Fraction,
) -> int:
    db.execute('BEGIN IMMEDIATE')
    with db:
        task_id = db.execute(
            '''INSERT INTO tasks (catalog_id, truth_revision_id, prediction_revision_id, threshold)
               VALUES (?, ?, ?, ?)''',
            (catalog_id, truth_revision_id, prediction_revision_id, str(threshold)),
        ).lastrowid
    return task_id


def get_task(db: sqlite3.Connection, task_id: int) -> FrozenTask:
    if type(task_id) is not int or not 0 < task_id < 2**63:
        raise KeyError(task_id)
    row = db.execute(
        '''SELECT catalog_id, truth_revision_id, prediction_revision_id, threshold
           FROM tasks WHERE id = ?''',
        (task_id,),
    ).fetchone()
    if row is None:
        raise KeyError(task_id)
    catalog_id, truth_revision_id, prediction_revision_id, threshold = row
    return FrozenTask(task_id, catalog_id, truth_revision_id, prediction_revision_id, Fraction(threshold))

import sqlite3
from fractions import Fraction

from reports.tie_model import TieMeanSnapshot

METRIC = 'tie_mean_ap'


def initialize_tie_reports(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS tie_mean_reports (
            id INTEGER PRIMARY KEY,
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            metric TEXT NOT NULL,
            ap TEXT NOT NULL
        )
    ''')


def insert_tie_mean_report(db: sqlite3.Connection, task_id: int, ap: Fraction) -> int:
    db.execute('BEGIN IMMEDIATE')
    with db:
        return db.execute(
            'INSERT INTO tie_mean_reports (task_id, metric, ap) VALUES (?, ?, ?)',
            (task_id, METRIC, str(ap)),
        ).lastrowid


def get_tie_mean_report(db: sqlite3.Connection, report_id: int) -> TieMeanSnapshot:
    if type(report_id) is not int or not 0 < report_id < 2**63:
        raise KeyError(report_id)
    row = db.execute(
        'SELECT task_id, metric, ap FROM tie_mean_reports WHERE id = ?', (report_id,)
    ).fetchone()
    if row is None:
        raise KeyError(report_id)
    task_id, metric, ap = row
    return TieMeanSnapshot(report_id, task_id, metric, Fraction(ap))

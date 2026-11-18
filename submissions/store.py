import sqlite3
from dataclasses import dataclass
from fractions import Fraction

from catalog.rectangles import pack_rectangle, unpack_rectangle
from submissions.rows import PredictionRow


@dataclass(frozen=True, slots=True)
class PredictionRevision:
    revision_id: int
    catalog_id: int
    submission_name: str
    rows: tuple[PredictionRow, ...]


def initialize_prediction_revisions(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS prediction_revisions (
            id INTEGER PRIMARY KEY,
            catalog_id INTEGER NOT NULL REFERENCES image_catalogs(id),
            submission_name TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS prediction_rows (
            revision_id INTEGER NOT NULL REFERENCES prediction_revisions(id),
            row_number INTEGER NOT NULL,
            prediction_id TEXT NOT NULL,
            image_id TEXT NOT NULL,
            x0 TEXT NOT NULL,
            y0 TEXT NOT NULL,
            x1 TEXT NOT NULL,
            y1 TEXT NOT NULL,
            score TEXT NOT NULL,
            PRIMARY KEY (revision_id, prediction_id),
            UNIQUE (revision_id, row_number)
        )
    ''')


def insert_prediction_revision(
    db: sqlite3.Connection, catalog_id: int, submission_name: str, rows: tuple[PredictionRow, ...]
) -> int:
    db.execute('BEGIN IMMEDIATE')
    with db:
        revision_id = db.execute(
            'INSERT INTO prediction_revisions (catalog_id, submission_name) VALUES (?, ?)',
            (catalog_id, submission_name),
        ).lastrowid
        db.executemany(
            '''INSERT INTO prediction_rows
               (revision_id, row_number, prediction_id, image_id, x0, y0, x1, y1, score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                (revision_id, number, row.prediction_id, row.image_id,
                 *pack_rectangle(row.rectangle), str(row.score))
                for number, row in enumerate(rows, 1)
            ),
        )
    return revision_id


def get_prediction_revision(db: sqlite3.Connection, revision_id: int) -> PredictionRevision:
    if type(revision_id) is not int or not 0 < revision_id < 2**63:
        raise KeyError(revision_id)
    header = db.execute(
        'SELECT catalog_id, submission_name FROM prediction_revisions WHERE id = ?', (revision_id,)
    ).fetchone()
    if header is None:
        raise KeyError(revision_id)
    records = db.execute(
        '''SELECT prediction_id, image_id, score, x0, y0, x1, y1 FROM prediction_rows
           WHERE revision_id = ? ORDER BY row_number''',
        (revision_id,),
    )
    rows = tuple(
        PredictionRow(prediction, image, unpack_rectangle(coords), Fraction(score))
        for prediction, image, score, *coords in records
    )
    return PredictionRevision(revision_id, header[0], header[1], rows)

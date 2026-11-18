import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass

from catalog.images import get_image_catalog
from catalog.rectangles import pack_rectangle, unpack_rectangle
from catalog.truth import TruthInput, TruthRow, validate_truth_rows


@dataclass(frozen=True, slots=True)
class TruthRevision:
    revision_id: int
    catalog_id: int
    rows: tuple[TruthRow, ...]


def initialize_truth_revisions(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS truth_revisions (
            id INTEGER PRIMARY KEY,
            catalog_id INTEGER NOT NULL REFERENCES image_catalogs(id)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS truth_rows (
            revision_id INTEGER NOT NULL REFERENCES truth_revisions(id),
            row_number INTEGER NOT NULL,
            image_id TEXT NOT NULL,
            truth_id TEXT NOT NULL,
            x0 TEXT NOT NULL,
            y0 TEXT NOT NULL,
            x1 TEXT NOT NULL,
            y1 TEXT NOT NULL,
            PRIMARY KEY (revision_id, image_id, truth_id),
            UNIQUE (revision_id, row_number)
        )
    ''')


def save_truth(db: sqlite3.Connection, catalog_id: int, rows: Iterable[TruthInput]) -> int:
    catalog = get_image_catalog(db, catalog_id)
    validated = validate_truth_rows(catalog, rows)
    db.execute('BEGIN IMMEDIATE')
    with db:
        revision_id = db.execute(
            'INSERT INTO truth_revisions (catalog_id) VALUES (?)', (catalog_id,)
        ).lastrowid
        db.executemany(
            '''INSERT INTO truth_rows
               (revision_id, row_number, image_id, truth_id, x0, y0, x1, y1)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                (revision_id, number, row.image_id, row.truth_id, *pack_rectangle(row.rectangle))
                for number, row in enumerate(validated, 1)
            ),
        )
    return revision_id


def get_truth_revision(db: sqlite3.Connection, revision_id: int) -> TruthRevision:
    if type(revision_id) is not int or not 0 < revision_id < 2**63:
        raise KeyError(revision_id)
    header = db.execute(
        'SELECT catalog_id FROM truth_revisions WHERE id = ?', (revision_id,)
    ).fetchone()
    if header is None:
        raise KeyError(revision_id)
    records = db.execute(
        '''SELECT image_id, truth_id, x0, y0, x1, y1 FROM truth_rows
           WHERE revision_id = ? ORDER BY row_number''',
        (revision_id,),
    )
    rows = tuple(TruthRow(image, truth, unpack_rectangle(coords)) for image, truth, *coords in records)
    return TruthRevision(revision_id, header[0], rows)

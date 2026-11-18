import sqlite3
from collections import defaultdict
from fractions import Fraction

from reports.model import FalsePositive, ImageMisses, ReportDiagnostics, ReportSnapshot


def initialize_reports(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            task_id INTEGER NOT NULL REFERENCES tasks(id),
            ap TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS report_images (
            report_id INTEGER NOT NULL REFERENCES reports(id),
            image_id TEXT NOT NULL,
            PRIMARY KEY (report_id, image_id)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS report_misses (
            report_id INTEGER NOT NULL,
            image_id TEXT NOT NULL,
            truth_id TEXT NOT NULL,
            PRIMARY KEY (report_id, image_id, truth_id),
            FOREIGN KEY (report_id, image_id) REFERENCES report_images(report_id, image_id)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS report_false_positives (
            report_id INTEGER NOT NULL,
            rank INTEGER NOT NULL CHECK (rank > 0),
            image_id TEXT NOT NULL,
            prediction_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            PRIMARY KEY (report_id, rank),
            FOREIGN KEY (report_id, image_id) REFERENCES report_images(report_id, image_id)
        )
    ''')


def insert_report(
    db: sqlite3.Connection, task_id: int, ap: Fraction, diagnostics: ReportDiagnostics
) -> int:
    db.execute('BEGIN IMMEDIATE')
    with db:
        report_id = db.execute(
            'INSERT INTO reports (task_id, ap) VALUES (?, ?)', (task_id, str(ap))
        ).lastrowid
        db.executemany(
            'INSERT INTO report_images (report_id, image_id) VALUES (?, ?)',
            ((report_id, image.image_id) for image in diagnostics.image_misses),
        )
        db.executemany(
            '''INSERT INTO report_false_positives (report_id, rank, image_id, prediction_id, reason)
               VALUES (?, ?, ?, ?, ?)''',
            (
                (report_id, row.rank, row.image_id, row.prediction_id, row.reason)
                for row in diagnostics.false_positives
            ),
        )
        db.executemany(
            'INSERT INTO report_misses (report_id, image_id, truth_id) VALUES (?, ?, ?)',
            (
                (report_id, image.image_id, truth_id)
                for image in diagnostics.image_misses for truth_id in image.truth_ids
            ),
        )
    return report_id


def get_report(db: sqlite3.Connection, report_id: int) -> ReportSnapshot:
    if type(report_id) is not int or not 0 < report_id < 2**63:
        raise KeyError(report_id)
    header = db.execute('SELECT task_id, ap FROM reports WHERE id = ?', (report_id,)).fetchone()
    if header is None:
        raise KeyError(report_id)
    task_id, ap = header
    missed = defaultdict(list)
    for image_id, truth_id in db.execute(
        'SELECT image_id, truth_id FROM report_misses WHERE report_id = ? ORDER BY image_id, truth_id',
        (report_id,),
    ):
        missed[image_id].append(truth_id)
    image_misses = tuple(
        ImageMisses(image_id, tuple(missed[image_id]))
        for (image_id,) in db.execute(
            'SELECT image_id FROM report_images WHERE report_id = ? ORDER BY image_id', (report_id,)
        )
    )
    false_positives = tuple(
        FalsePositive(*row)
        for row in db.execute(
            '''SELECT rank, image_id, prediction_id, reason FROM report_false_positives
               WHERE report_id = ? ORDER BY rank''',
            (report_id,),
        )
    )
    return ReportSnapshot(report_id, task_id, Fraction(ap), ReportDiagnostics(image_misses, false_positives))

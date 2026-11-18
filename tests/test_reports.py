import sqlite3
from fractions import Fraction

from catalog.images import Image, get_image_catalog
from catalog.rectangles import Rectangle
from catalog.revisions import get_truth_revision
from ledger import freeze_task, initialize, issue_report, read_report, save_predictions, save_truth
from reports.model import FalsePositive, ImageMisses
from submissions.store import get_prediction_revision
from tasks.store import get_task
from tests.fixture import LedgerCase


REPORT_TABLES = ('reports', 'report_images', 'report_misses', 'report_false_positives')


class ReportTests(LedgerCase):
    def report_inputs(self):
        catalog = self.images()
        truth = save_truth(self.db, catalog, [('a', 'A', (0, 0, 1, 1)), ('a', 'B', (2, 0, 3, 1))])
        predictions = save_predictions(self.db, catalog, 'vendor', [
            ('hit', 'a', (0, 0, 1, 1), '1/3'), ('alarm', 'z', (0, 0, 1, 1), '2/3'),
        ])
        task = freeze_task(self.db, truth, predictions, '1/2')
        return catalog, truth, predictions, task

    def check_original_report(self, report, task):
        self.assertIsInstance(report.ap, Fraction)
        self.assertEqual((report.task_id, report.ap), (task, Fraction(1, 4)))
        self.assertEqual(report.diagnostics.image_misses, (ImageMisses('a', ('B',)), ImageMisses('z', ())))
        self.assertEqual(report.diagnostics.false_positives, (FalsePositive(1, 'z', 'alarm', 'no_truth'),))

    def test_v8_rollback_diagnostics_and_retry(self):
        _, _, _, task = self.report_inputs()
        original_id = issue_report(self.db, task)
        original = read_report(self.db, original_id)
        self.db.execute('''
            CREATE TRIGGER block_miss BEFORE INSERT ON report_misses
            BEGIN
                SELECT RAISE(ABORT, 'test diagnostic write rejected');
            END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'test diagnostic write rejected'):
            issue_report(self.db, task)
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.counts(*REPORT_TABLES), (1, 2, 1, 1))
        self.assertEqual(read_report(self.db, original_id), original)
        self.db.execute('DROP TRIGGER block_miss')
        retry_id = issue_report(self.db, task)
        self.assertNotEqual(retry_id, original_id)
        self.check_original_report(read_report(self.db, retry_id), task)
        self.assertEqual(self.counts(*REPORT_TABLES), (2, 4, 2, 2))

    def test_v8_deferred_commit_failure(self):
        _, _, _, task = self.report_inputs()
        self.db.executescript('''
            CREATE TABLE test_allowed_key (id INTEGER PRIMARY KEY);
            CREATE TABLE test_commit_guard (
                id INTEGER REFERENCES test_allowed_key(id) DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER reject_commit AFTER INSERT ON report_misses
            BEGIN
                INSERT INTO test_commit_guard VALUES (1);
            END;
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
            issue_report(self.db, task)
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.counts(*REPORT_TABLES, 'test_commit_guard'), (0, 0, 0, 0, 0))
        self.db.execute('DROP TRIGGER reject_commit')
        self.check_original_report(read_report(self.db, issue_report(self.db, task)), task)

    def test_v8_unknown_task(self):
        self.report_inputs()
        with self.assertRaises(KeyError):
            issue_report(self.db, 99999)
        self.assertEqual(self.counts(*REPORT_TABLES), (0, 0, 0, 0))

    def test_v9_reopen_original_report_and_unknown_id(self):
        catalog, truth, predictions, task = self.report_inputs()
        report_id = issue_report(self.db, task)
        original = read_report(self.db, report_id)
        correction = save_truth(self.db, catalog, [('a', 'A', (1, 1, 2, 2))])
        self.assertNotEqual(correction, truth)
        revised_task = freeze_task(self.db, correction, predictions, '1/2')
        self.assertEqual(read_report(self.db, issue_report(self.db, revised_task)).ap, 0)
        self.reopen()
        recovered = read_report(self.db, report_id)
        self.assertEqual(recovered, original)
        self.check_original_report(recovered, task)
        with self.assertRaises(KeyError):
            read_report(self.db, 99999)

    def test_v9_snapshot_only(self):
        catalog, _, _, task = self.report_inputs()
        report_id = issue_report(self.db, task)
        expected = read_report(self.db, report_id)
        save_truth(self.db, catalog, [('a', 'A', (1, 1, 2, 2))])
        self.reopen()

        def authorize(action, table, column, database, source):
            if action == sqlite3.SQLITE_READ and table not in REPORT_TABLES:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        self.db.set_authorizer(authorize)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                self.db.execute('SELECT threshold FROM tasks').fetchall()
            recovered = read_report(self.db, report_id)
        finally:
            self.db.set_authorizer(None)
        self.assertEqual(recovered, expected)
        self.check_original_report(recovered, task)

    def test_v9_idempotent_init(self):
        catalog, truth, submitted, task = self.report_inputs()
        report_id = issue_report(self.db, task)
        correction = save_truth(self.db, catalog, [('a', 'A', ('1/3', 0, 1, 1))])
        new_submission = save_predictions(self.db, catalog, 'vendor', [('new', 'a', (0, 0, 1, 1), '7/8')])
        tables = ('image_catalogs', 'catalog_images', 'truth_revisions', 'truth_rows',
                  'prediction_revisions', 'prediction_rows', 'tasks', *REPORT_TABLES)
        initialize(self.db)
        self.reopen()
        initialize(self.db)
        self.assertEqual(self.counts(*tables), (1, 2, 2, 3, 2, 3, 1, 1, 2, 1, 1))
        saved_catalog = get_image_catalog(self.db, catalog)
        self.assertEqual(saved_catalog.images, (Image('a', 4, 4), Image('z', 4, 4)))
        self.assertEqual(get_truth_revision(self.db, truth).rows[0].rectangle, Rectangle(0, 0, 1, 1))
        self.assertEqual(get_truth_revision(self.db, correction).rows[0].rectangle.x0, Fraction(1, 3))
        self.assertEqual(get_prediction_revision(self.db, submitted).rows[0].prediction_id, 'hit')
        self.assertEqual(get_prediction_revision(self.db, new_submission).rows[0].score, Fraction(7, 8))
        self.assertEqual(get_task(self.db, task).truth_revision_id, truth)
        self.assertEqual(get_task(self.db, task).prediction_revision_id, submitted)
        self.check_original_report(read_report(self.db, report_id), task)

import sqlite3
from fractions import Fraction
from itertools import permutations
from math import factorial

from ledger import (
    Image,
    freeze_task,
    initialize,
    issue_report,
    issue_tie_mean,
    put_images,
    read_report,
    read_tie_mean,
    save_predictions,
    save_truth,
)
from matching.tie import (
    build_high_segment,
    continue_order,
    mean_average_precision,
    split_lowest_scores,
)
from tasks.inputs import load_task_inputs
from tests.fixture import LedgerCase
from tests.test_tie_mean_fixture import PREDICTION_ROWS, THRESHOLD, TRUTH_ROWS

TIE_TABLES = ('tie_mean_reports',)


def brute_force_mean(inputs) -> Fraction:
    """Explicitly average V1 AP over every lowest-group ordering."""

    higher, lowest = split_lowest_scores(inputs.predictions.rows)
    high = build_high_segment(inputs, higher)
    truth_count = len(inputs.truth.rows)
    total = Fraction(0)
    orders = tuple(permutations(lowest)) if lowest else ((),)
    for order in orders:
        trace = continue_order(inputs, high, order)
        precision = sum(
            (Fraction(entry.cumulative_hits, entry.rank)
             for entry in trace.entries if entry.truth_id is not None),
            Fraction(0),
        )
        total += precision / truth_count
    return total / len(orders)


class TieMeanCalculationTests(LedgerCase):
    def sample_task(self):
        catalog = self.images()
        truth = save_truth(self.db, catalog, TRUTH_ROWS)
        submitted = save_predictions(self.db, catalog, 'vendor', PREDICTION_ROWS)
        return catalog, truth, submitted, freeze_task(self.db, truth, submitted, THRESHOLD)

    def test_competition_mean_matches_documented_value(self):
        _, _, _, task = self.sample_task()
        inputs = load_task_inputs(self.db, task)
        self.assertEqual(mean_average_precision(inputs, len(inputs.truth.rows)), Fraction(11, 18))
        self.assertEqual(brute_force_mean(inputs), Fraction(11, 18))
        report = read_tie_mean(self.db, issue_tie_mean(self.db, task))
        self.assertEqual((report.task_id, report.metric, report.ap), (task, 'tie_mean_ap', Fraction(11, 18)))

    def test_v1_report_of_same_rows_stays_unchanged(self):
        _, _, _, task = self.sample_task()
        # V1 orders the three equal scores by prediction ID: F, N, Z.
        self.assertEqual(read_report(self.db, issue_report(self.db, task)).ap, Fraction(1, 2))
        self.assertEqual(read_tie_mean(self.db, issue_tie_mean(self.db, task)).ap, Fraction(11, 18))

    def test_reordered_rows_keep_the_mean(self):
        catalog, truth, _, task = self.sample_task()
        reordered = save_predictions(self.db, catalog, 'vendor', reversed(PREDICTION_ROWS))
        other = freeze_task(self.db, truth, reordered, THRESHOLD)
        self.assertEqual(read_tie_mean(self.db, issue_tie_mean(self.db, other)).ap, Fraction(11, 18))
        self.assertEqual(brute_force_mean(load_task_inputs(self.db, other)), Fraction(11, 18))

    def test_high_prediction_keeps_lowest_group_competition(self):
        catalog, truth, _, _ = self.sample_task()
        rows = [
            ('H', 'a', (0, 0, 2, 2), '1'),
            ('F', 'a', (0, 0, 2, 2), '1/3'),
            ('N', 'a', (1, 0, 2, 2), '2/6'),
        ]
        submitted = save_predictions(self.db, catalog, 'high', rows)
        task = freeze_task(self.db, truth, submitted, THRESHOLD)
        inputs = load_task_inputs(self.db, task)
        self.assertEqual(mean_average_precision(inputs, len(inputs.truth.rows)), Fraction(11, 12))
        self.assertEqual(brute_force_mean(inputs), Fraction(11, 12))
        self.assertEqual(read_tie_mean(self.db, issue_tie_mean(self.db, task)).ap, Fraction(11, 12))

    def test_added_truth_on_the_empty_image(self):
        catalog, _, submitted, _ = self.sample_task()
        corrected = save_truth(self.db, catalog, [*TRUTH_ROWS, ('z', 'C', (0, 0, 1, 1))])
        task = freeze_task(self.db, corrected, submitted, THRESHOLD)
        inputs = load_task_inputs(self.db, task)
        self.assertEqual(mean_average_precision(inputs, len(inputs.truth.rows)), Fraction(22, 27))
        self.assertEqual(brute_force_mean(inputs), Fraction(22, 27))

    def test_empty_predictions_are_zero(self):
        catalog = self.images()
        truth = save_truth(self.db, catalog, TRUTH_ROWS)
        submitted = save_predictions(self.db, catalog, 'empty', [])
        task = freeze_task(self.db, truth, submitted, THRESHOLD)
        inputs = load_task_inputs(self.db, task)
        self.assertEqual(mean_average_precision(inputs, len(inputs.truth.rows)), Fraction(0))
        self.assertEqual(read_tie_mean(self.db, issue_tie_mean(self.db, task)).ap, Fraction(0))


class TieMeanCapacityTests(LedgerCase):
    def full_capacity_task(self, empty_images=31):
        names = ['a'] + [f'z{index:02d}' for index in range(1, empty_images + 1)]
        catalog = put_images(self.db, 'full', [Image(name, 4, 4) for name in names])
        truth = save_truth(self.db, catalog, [('a', 'A', (0, 0, 2, 2)), ('a', 'B', (0, 0, 1, 2))])
        rows = [
            ('F', 'a', (0, 0, 2, 2), '1/3'),
            ('N', 'a', (1, 0, 2, 2), '2/6'),
            ('a-fp1', 'a', (3, 0, 4, 1), '3/9'),
            ('a-fp2', 'a', (3, 0, 4, 1), '3/9'),
        ]
        for name in names[1:]:
            for slot in range(4):
                rows.append((f'{name}-{slot}', name, (0, 0, 1, 1), '1/3'))
        if empty_images == 31:
            self.assertEqual(len(rows), 128)
        submitted = save_predictions(self.db, catalog, 'vendor', rows)
        return freeze_task(self.db, truth, submitted, THRESHOLD)

    def test_documented_full_capacity_mean(self):
        task = self.full_capacity_task()
        expected = sum((Fraction(1, rank) for rank in range(1, 129)), Fraction(0)) / 128
        report = read_tie_mean(self.db, issue_tie_mean(self.db, task))
        self.assertEqual(report.ap, expected)

    def test_too_many_images_are_rejected(self):
        task = self.full_capacity_task(empty_images=32)
        with self.assertRaises(ValueError):
            issue_tie_mean(self.db, task)
        self.assertEqual(self.counts(*TIE_TABLES), (0,))

    def test_too_many_lowest_predictions_in_one_image_are_rejected(self):
        catalog = self.images()
        truth = save_truth(self.db, catalog, [('a', 'A', (0, 0, 2, 2))])
        rows = [(f'p{slot}', 'a', (0, 0, 1, 1), '1/3') for slot in range(5)]
        submitted = save_predictions(self.db, catalog, 'vendor', rows)
        task = freeze_task(self.db, truth, submitted, '1/2')
        with self.assertRaises(ValueError):
            issue_tie_mean(self.db, task)
        self.assertEqual(self.counts(*TIE_TABLES), (0,))

    def test_high_segment_keeps_the_v1_input_boundary(self):
        # Only the lowest group is capped; a higher-score crowd is still V1's business.
        catalog = self.images()
        truth = save_truth(self.db, catalog, [('a', 'A', (0, 0, 2, 2))])
        rows = [(f'h{slot}', 'a', (0, 0, 1, 1), '1') for slot in range(9)]
        rows.append(('low', 'a', (0, 0, 1, 1), '1/3'))
        submitted = save_predictions(self.db, catalog, 'vendor', rows)
        task = freeze_task(self.db, truth, submitted, '3/4')
        report = read_tie_mean(self.db, issue_tie_mean(self.db, task))
        self.assertEqual(report.metric, 'tie_mean_ap')
        self.assertIsInstance(report.ap, Fraction)

    def test_limits_include_the_endpoint(self):
        # Four lowest predictions on one image and 32 catalog images are legal.
        task = self.full_capacity_task(empty_images=31)
        self.assertIsInstance(issue_tie_mean(self.db, task), int)


class TieMeanReportTests(LedgerCase):
    def prepare(self):
        catalog = self.images()
        truth = save_truth(self.db, catalog, TRUTH_ROWS)
        submitted = save_predictions(self.db, catalog, 'vendor', PREDICTION_ROWS)
        return catalog, truth, submitted, freeze_task(self.db, truth, submitted, THRESHOLD)

    def test_unknown_ids_raise_key_error(self):
        _, _, _, task = self.prepare()
        with self.assertRaises(KeyError):
            issue_tie_mean(self.db, 99999)
        with self.assertRaises(KeyError):
            read_tie_mean(self.db, 99999)
        with self.assertRaises(KeyError):
            read_tie_mean(self.db, 'x')
        self.assertEqual(self.counts(*TIE_TABLES), (0,))

    def test_v1_report_id_is_not_a_tie_mean_report(self):
        catalog, truth, submitted, task = self.prepare()
        original = issue_report(self.db, task)
        with self.assertRaises(KeyError):
            read_tie_mean(self.db, original)
        self.assertEqual(read_report(self.db, original).task_id, task)

    def test_write_failure_rolls_back_and_retry_succeeds(self):
        _, _, _, task = self.prepare()
        original_id = issue_tie_mean(self.db, task)
        original = read_tie_mean(self.db, original_id)
        self.db.execute('''
            CREATE TRIGGER block_tie BEFORE INSERT ON tie_mean_reports
            BEGIN
                SELECT RAISE(ABORT, 'test tie write rejected');
            END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'test tie write rejected'):
            issue_tie_mean(self.db, task)
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.counts(*TIE_TABLES), (1,))
        self.assertEqual(read_tie_mean(self.db, original_id), original)
        self.db.execute('DROP TRIGGER block_tie')
        retry_id = issue_tie_mean(self.db, task)
        self.assertNotEqual(retry_id, original_id)
        retry = read_tie_mean(self.db, retry_id)
        self.assertEqual((retry.task_id, retry.metric, retry.ap),
                         (original.task_id, original.metric, original.ap))

    def test_commit_failure_rolls_back(self):
        _, _, _, task = self.prepare()
        self.db.executescript('''
            CREATE TABLE tie_allowed_key (id INTEGER PRIMARY KEY);
            CREATE TABLE tie_commit_guard (
                id INTEGER REFERENCES tie_allowed_key(id) DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER reject_tie_commit AFTER INSERT ON tie_mean_reports
            BEGIN
                INSERT INTO tie_commit_guard VALUES (1);
            END;
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
            issue_tie_mean(self.db, task)
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.counts(*TIE_TABLES, 'tie_commit_guard'), (0, 0))
        self.db.execute('DROP TRIGGER reject_tie_commit')
        self.assertEqual(read_tie_mean(self.db, issue_tie_mean(self.db, task)).ap, Fraction(11, 18))

    def test_snapshot_only_read(self):
        _, _, _, task = self.prepare()
        report_id = issue_tie_mean(self.db, task)
        expected = read_tie_mean(self.db, report_id)
        self.reopen()

        def authorize(action, table, column, database, source):
            if action == sqlite3.SQLITE_READ and table not in TIE_TABLES:
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        self.db.set_authorizer(authorize)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                self.db.execute('SELECT threshold FROM tasks').fetchall()
            recovered = read_tie_mean(self.db, report_id)
        finally:
            self.db.set_authorizer(None)
        self.assertEqual(recovered, expected)

    def test_corrections_and_reopen_keep_the_issued_value(self):
        catalog, truth, _, task = self.prepare()
        report_id = issue_tie_mean(self.db, task)
        issued = read_tie_mean(self.db, report_id)
        save_truth(self.db, catalog, [*TRUTH_ROWS, ('z', 'C', (0, 0, 1, 1))])
        save_predictions(self.db, catalog, 'vendor', [('X', 'z', (0, 0, 1, 1), '0')])
        self.reopen()
        initialize(self.db)
        self.assertEqual(read_tie_mean(self.db, report_id), issued)
        self.assertEqual(read_report(self.db, issue_report(self.db, task)).ap, Fraction(1, 2))
        self.assertEqual(self.counts(*TIE_TABLES), (1,))


class TieMeanEvidenceTests(LedgerCase):
    def test_orders_share_the_same_high_handoff(self):
        catalog = self.images()
        truth = save_truth(self.db, catalog, TRUTH_ROWS)
        submitted = save_predictions(self.db, catalog, 'vendor', [
            ('H', 'a', (0, 0, 2, 2), '1'),
            ('F', 'a', (0, 0, 2, 2), '1/3'),
            ('N', 'a', (1, 0, 2, 2), '2/6'),
            ('Z', 'z', (0, 0, 1, 1), '3/9'),
        ])
        task = freeze_task(self.db, truth, submitted, THRESHOLD)
        inputs = load_task_inputs(self.db, task)
        higher, lowest = split_lowest_scores(inputs.predictions.rows)
        high = build_high_segment(inputs, higher)
        traces = [continue_order(inputs, high, order) for order in permutations(lowest)]
        self.assertEqual(len(traces), factorial(len(lowest)))
        self.assertEqual({trace.entries[: high.size] for trace in traces}, {high.entries})
        for trace in traces:
            ranks = [entry.rank for entry in trace.entries]
            self.assertEqual(ranks, list(range(1, len(ranks) + 1)))
            hits = 0
            for entry in trace.entries:
                hits += entry.truth_id is not None
                self.assertEqual(entry.cumulative_hits, hits)
            # Same-image occupancy handed over by the high segment is respected.
            self.assertEqual(trace.entries[0].truth_id, 'A')
            self.assertFalse(any(
                entry.truth_id == 'A' and entry is not trace.entries[0]
                for entry in trace.entries
            ))
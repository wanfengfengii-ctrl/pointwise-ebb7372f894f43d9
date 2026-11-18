from fractions import Fraction

from ledger import issue_report, read_report
from matching.greedy import build_trace
from matching.trace import MissReason
from reports.model import FalsePositive, ImageMisses
from tasks.inputs import load_task_inputs
from tests.fixture import LedgerCase


class EvaluationTests(LedgerCase):
    def trace_and_report(self, task):
        trace = build_trace(load_task_inputs(self.db, task))
        return trace, read_report(self.db, issue_report(self.db, task))

    def test_v6_closed_iou_tie_uses_smallest_truth_id(self):
        task = self.prepare_task(
            [('a', 'B', (1, 0, 2, 2)), ('a', 'A', (0, 0, 1, 2))],
            [('p2', 'a', (0, 0, 1, 2), 1), ('p1', 'a', (0, 0, 2, 2), 1)],
        )
        trace, report = self.trace_and_report(task)
        self.assertEqual(trace.task_id, task)
        self.assertEqual(
            [(entry.rank, entry.prediction_id, entry.truth_id, entry.miss_reason) for entry in trace.entries],
            [(1, 'p1', 'A', None), (2, 'p2', None, MissReason.OCCUPIED)],
        )
        self.assertEqual(report.ap, Fraction(1, 2))
        self.assertEqual(report.diagnostics.image_misses, (ImageMisses('a', ('B',)), ImageMisses('z', ())))
        self.assertEqual(report.diagnostics.false_positives, (FalsePositive(2, 'a', 'p2', 'occupied'),))

    def test_v6_closed_gate(self):
        truths = [('a', 'A', (0, 0, 2, 2))]
        for box, ap, reason in [
            ((0, 0, 1, 2), 1, None),
            ((0, 0, '99/100', 2), 0, MissReason.BELOW_THRESHOLD),
            ((2, 0, 3, 2), 0, MissReason.BELOW_THRESHOLD),
        ]:
            with self.subTest(box=box):
                task = self.prepare_task(truths, [('P', 'a', box, 1)])
                trace, report = self.trace_and_report(task)
                self.assertEqual(trace.entries[0].miss_reason, reason)
                self.assertEqual(trace.entries[0].truth_id, 'A' if ap else None)
                self.assertEqual(report.ap, Fraction(ap))
                self.assertEqual(report.diagnostics.image_misses[0].truth_ids, () if ap else ('A',))

    def test_v6_occupied_fallback(self):
        for threshold in ['1/3', '1/2']:
            with self.subTest(threshold=threshold):
                task = self.prepare_task(
                    [('a', 'B', (1, 0, 2, 2)), ('a', 'A', (0, 0, 1, 2))],
                    [('cover', 'a', (0, 0, 2, 2), '1/2'), ('first', 'a', (0, 0, 1, 2), 1)],
                    threshold,
                )
                trace, report = self.trace_and_report(task)
                self.assertEqual([(row.prediction_id, row.truth_id) for row in trace.entries],
                                 [('first', 'A'), ('cover', 'B')])
                self.assertEqual(report.ap, Fraction(1))
                self.assertEqual(report.diagnostics.false_positives, ())
                self.assertEqual(report.diagnostics.image_misses,
                                 (ImageMisses('a', ()), ImageMisses('z', ())))

    def test_v6_image_local_identity(self):
        task = self.prepare_task(
            [('a', 'T', (0, 0, 1, 1)), ('z', 'T', (0, 0, 1, 1))],
            [('p-a', 'a', (0, 0, 1, 1), 1), ('p-z', 'z', (0, 0, 1, 1), 1)],
        )
        trace, report = self.trace_and_report(task)
        self.assertEqual(trace.matched_truth_keys(), frozenset({('a', 'T'), ('z', 'T')}))
        self.assertEqual(report.ap, Fraction(1))
        self.assertEqual(report.diagnostics.image_misses, (ImageMisses('a', ()), ImageMisses('z', ())))

    def test_v7_global_order(self):
        truths = [('a', 'T', (0, 0, 2, 2))]
        hit = ('a-hit', 'a', (0, 0, 2, 2), '1/3')
        for alarm_score, order, ap in [
            ('2/3', ['z-alarm', 'a-hit'], Fraction(1, 2)),
            ('2/6', ['a-hit', 'z-alarm'], Fraction(1)),
        ]:
            alarm = ('z-alarm', 'z', (0, 0, 1, 1), alarm_score)
            for rows in [(hit, alarm), (alarm, hit)]:
                with self.subTest(rows=rows):
                    task = self.prepare_task(truths, rows)
                    trace, report = self.trace_and_report(task)
                    self.assertEqual([(row.rank, row.prediction_id) for row in trace.entries], list(enumerate(order, 1)))
                    self.assertEqual(report.ap, ap)
                    self.assertEqual(report.diagnostics.false_positives,
                                     (FalsePositive(order.index('z-alarm') + 1, 'z', 'z-alarm', 'no_truth'),))

    def test_v7_diagnostic_identity(self):
        task = self.prepare_task(
            [('a', 'T', (0, 0, 2, 2))],
            [('hit', 'a', (0, 0, 2, 2), '1/3'), ('alarm', 'z', (0, 0, 1, 1), '2/3')],
        )
        report = read_report(self.db, issue_report(self.db, task))
        self.assertEqual(report.task_id, task)
        self.assertEqual(report.ap, Fraction(1, 2))
        self.assertEqual(report.diagnostics.false_positives, (FalsePositive(1, 'z', 'alarm', 'no_truth'),))
        self.assertEqual(report.diagnostics.image_misses, (ImageMisses('a', ()), ImageMisses('z', ())))

    def test_v7_empty_predictions(self):
        task = self.prepare_task(
            [('a', 'B', (1, 0, 2, 1)), ('a', 'A', (0, 0, 1, 1))], [],
        )
        trace, report = self.trace_and_report(task)
        self.assertEqual(trace.entries, ())
        self.assertIsInstance(report.ap, Fraction)
        self.assertEqual(report.ap, 0)
        self.assertEqual(report.diagnostics.false_positives, ())
        self.assertEqual(report.diagnostics.image_misses, (ImageMisses('a', ('A', 'B')), ImageMisses('z', ())))

from fractions import Fraction

from ledger import freeze_task, issue_report, read_report, save_predictions, save_truth
from tests.fixture import LedgerCase

TRUTH_ROWS = (
    ("a", "A", (0, 0, 2, 2)),
    ("a", "B", (0, 0, 1, 2)),
)
PREDICTION_ROWS = (
    ("F", "a", (0, 0, 2, 2), "1/3"),
    ("N", "a", (1, 0, 2, 2), "2/6"),
    ("Z", "z", (0, 0, 1, 1), "3/9"),
)
THRESHOLD = "1/2"


class TieMeanFixtureTests(LedgerCase):
    def test_competition_fixture_has_distinct_v1_outcomes(self):
        catalog_id = self.images()
        truth_id = save_truth(self.db, catalog_id, TRUTH_ROWS)
        by_id = {row[0]: row for row in PREDICTION_ROWS}
        expectations = (
            ("FNZ", "1/2"), ("FZN", "1/2"), ("NFZ", "1"),
            ("NZF", "5/6"), ("ZFN", "1/4"), ("ZNF", "7/12"),
        )
        for order, expected in expectations:
            with self.subTest(order=order):
                # V1 breaks score ties by ID. Number the rows to force this order.
                rows = [
                    (f"{index}-{role}", *by_id[role][1:])
                    for index, role in enumerate(order, 1)
                ]
                revision_id = save_predictions(self.db, catalog_id, "fixture", reversed(rows))
                task_id = freeze_task(self.db, truth_id, revision_id, THRESHOLD)
                report = read_report(self.db, issue_report(self.db, task_id))
                self.assertEqual(report.ap, Fraction(expected))

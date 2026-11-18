from fractions import Fraction

from catalog.images import get_image_catalog
from catalog.rectangles import Rectangle
from ledger import Image, freeze_task, issue_report, put_images, read_report, save_predictions, save_truth
from tasks.inputs import load_task_inputs
from tasks.store import FrozenTask, get_task
from tests.fixture import LedgerCase


class TaskTests(LedgerCase):
    def test_v4_fixed_inputs(self):
        catalog = self.images()
        first_truth = save_truth(self.db, catalog, [('a', 'T', (0, 0, 1, 1))])
        first_prediction = save_predictions(self.db, catalog, 'vendor', [('old', 'a', (0, 0, 1, 1), '2/3')])
        first_task = freeze_task(self.db, first_truth, first_prediction, '2/3')
        before = read_report(self.db, issue_report(self.db, first_task))
        new_truth = save_truth(self.db, catalog, [('a', 'T', (2, 0, 3, 1))])
        new_prediction = save_predictions(self.db, catalog, 'vendor', [('new', 'z', (0, 0, 1, 1), '1/3')])
        new_task = freeze_task(self.db, new_truth, new_prediction, '1/2')
        self.reopen()
        expected_task = FrozenTask(first_task, catalog, first_truth, first_prediction, Fraction(2, 3))
        self.assertEqual(get_task(self.db, first_task), expected_task)
        inputs = load_task_inputs(self.db, first_task)
        self.assertEqual(inputs.task, expected_task)
        self.assertEqual(inputs.catalog, get_image_catalog(self.db, catalog))
        self.assertEqual(inputs.catalog.images, (Image('a', 4, 4), Image('z', 4, 4)))
        self.assertEqual((inputs.truth.revision_id, inputs.truth.catalog_id), (first_truth, catalog))
        self.assertEqual((inputs.predictions.revision_id, inputs.predictions.catalog_id), (first_prediction, catalog))
        self.assertEqual(
            [(row.image_id, row.truth_id, row.rectangle) for row in inputs.truth.rows],
            [('a', 'T', Rectangle(0, 0, 1, 1))],
        )
        self.assertEqual(
            [(row.prediction_id, row.image_id, row.rectangle, row.score) for row in inputs.predictions.rows],
            [('old', 'a', Rectangle(0, 0, 1, 1), Fraction(2, 3))],
        )
        reissued = read_report(self.db, issue_report(self.db, first_task))
        self.assertEqual((before.ap, reissued.ap, reissued.task_id), (1, 1, first_task))
        self.assertEqual(reissued.diagnostics, before.diagnostics)
        self.assertEqual(read_report(self.db, issue_report(self.db, new_task)).ap, 0)

    def test_v5_same_image_names_across_catalogs_do_not_bind(self):
        first = put_images(self.db, 'batch', [Image('same', 4, 4)])
        second = put_images(self.db, 'batch', [Image('same', 4, 4)])
        truth = save_truth(self.db, first, [('same', 'T', (0, 0, 1, 1))])
        prediction = save_predictions(self.db, second, 'vendor', [('P', 'same', (0, 0, 1, 1), 1)])
        with self.assertRaises(ValueError):
            freeze_task(self.db, truth, prediction, '1/2')
        self.assertEqual(self.counts('tasks'), (0,))

    def test_v5_task_rejections(self):
        catalog = self.images()
        empty_truth = save_truth(self.db, catalog, [])
        truth = save_truth(self.db, catalog, [('a', 'T', (0, 0, 1, 1))])
        prediction = save_predictions(self.db, catalog, 'empty', [])
        valid = freeze_task(self.db, truth, prediction, 1)
        self.assertEqual(get_task(self.db, valid).threshold, Fraction(1))
        for annotation, threshold in [(empty_truth, 1), (truth, 0), (truth, '11/10'), (truth, 'x')]:
            with self.subTest(annotation=annotation, threshold=threshold):
                with self.assertRaises(ValueError):
                    freeze_task(self.db, annotation, prediction, threshold)
                self.assertEqual(self.counts('tasks'), (1,))
        for annotation, submitted in [(99999, prediction), (truth, 99999)]:
            with self.subTest(annotation=annotation, submitted=submitted):
                with self.assertRaises(KeyError):
                    freeze_task(self.db, annotation, submitted, '1/2')
                self.assertEqual(self.counts('tasks'), (1,))

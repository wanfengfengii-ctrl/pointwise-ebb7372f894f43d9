from fractions import Fraction

from catalog.images import get_image_catalog
from catalog.rectangles import Rectangle
from catalog.revisions import get_truth_revision
from ledger import Image, put_images, save_predictions, save_truth
from submissions.store import get_prediction_revision
from tests.fixture import LedgerCase


class IntakeTests(LedgerCase):
    def test_v1_keeps_empty_image_available(self):
        catalog = self.images()
        truth = save_truth(self.db, catalog, [('a', 'T', (0, 0, 2, 2))])
        predictions = save_predictions(self.db, catalog, 'vendor', [
            ('a-hit', 'a', (0, 0, 2, 2), '1/3'),
            ('z-alarm', 'z', (0, 0, 1, 1), '2/3'),
        ])
        self.assertEqual(get_image_catalog(self.db, catalog).images, (Image('a', 4, 4), Image('z', 4, 4)))
        self.assertEqual([row.image_id for row in get_truth_revision(self.db, truth).rows], ['a'])
        self.assertEqual(
            [(row.prediction_id, row.image_id) for row in get_prediction_revision(self.db, predictions).rows],
            [('a-hit', 'a'), ('z-alarm', 'z')],
        )

    def test_v1_manifest_guard(self):
        catalog = self.images()
        cases = [
            [], [Image('good', 4, 4), Image('bad', 0, 4)],
            [Image('bad', 4, -1)], [Image('bad', 2.5, 4)], [Image('bad', True, 4)],
            [Image('same', 4, 4), Image('same', 2, 2)],
        ]
        for images in cases:
            with self.subTest(images=images):
                with self.assertRaises(ValueError):
                    put_images(self.db, 'rejected', images)
                self.assertEqual(self.counts('image_catalogs', 'catalog_images'), (1, 2))
        self.assertEqual(get_image_catalog(self.db, catalog).batch_name, 'shift-one')

    def test_v1_scoped_image(self):
        wide = put_images(self.db, 'batch', [Image('same', 4, 4)])
        narrow = put_images(self.db, 'batch', [Image('same', 2, 4)])
        rows = [('P', 'same', (0, 0, 3, 1), 1)]
        with self.assertRaises(ValueError):
            save_predictions(self.db, narrow, 'vendor', rows)
        self.assertEqual(self.counts('prediction_revisions', 'prediction_rows'), (0, 0))
        accepted = save_predictions(self.db, wide, 'vendor', rows)
        result = get_prediction_revision(self.db, accepted)
        self.assertEqual(result.catalog_id, wide)
        self.assertEqual(result.rows[0].rectangle.x1, 3)

    def test_v1_unknown_catalog_and_foreign_images(self):
        with self.assertRaises(KeyError):
            save_truth(self.db, 999, [])
        with self.assertRaises(KeyError):
            save_predictions(self.db, 999, 'vendor', [])
        catalog = self.images()
        with self.assertRaises(ValueError):
            save_truth(self.db, catalog, [('outside', 'T', (0, 0, 1, 1))])
        with self.assertRaises(ValueError):
            save_predictions(self.db, catalog, 'vendor', [('P', 'outside', (0, 0, 1, 1), 1)])
        self.assertEqual(self.counts('truth_revisions', 'truth_rows', 'prediction_revisions', 'prediction_rows'), (0, 0, 0, 0))

    def test_v2_outside_rectangle_rejects_entire_revision(self):
        catalog = self.images()
        with self.assertRaises(ValueError):
            save_truth(self.db, catalog, [
                ('a', 'valid', (0, 0, 2, 2)), ('z', 'outside', (0, 0, 5, 1)),
            ])
        self.assertEqual(self.counts('truth_revisions', 'truth_rows'), (0, 0))

    def test_v2_exact_bounds(self):
        catalog = put_images(self.db, 'narrow', [Image('a', 2, 2)])
        original = save_truth(self.db, catalog, [('a', 'edge', ('19/10', 0, 2, 2))])
        expected = Rectangle(Fraction(19, 10), Fraction(0), Fraction(2), Fraction(2))
        saved = get_truth_revision(self.db, original)
        self.assertEqual(saved.rows[0].rectangle, expected)
        self.assertEqual(saved.rows[0].rectangle.area, Fraction(1, 5))
        for bad_box in [(0, 0, '21/10', 1), (1, 0, 1, 1), (0, 1, 1, 0), ('-1/10', 0, 1, 1)]:
            with self.subTest(box=bad_box):
                with self.assertRaises(ValueError):
                    save_truth(self.db, catalog, [
                        ('a', 'valid', (0, 0, 2, 2)), ('a', 'invalid', bad_box),
                    ])
                self.assertEqual(self.counts('truth_revisions', 'truth_rows'), (1, 1))
        self.assertEqual(get_truth_revision(self.db, original), saved)

    def test_v2_truth_identity(self):
        catalog = self.images()
        row = ('a', 'T', (0, 0, 1, 1))
        with self.assertRaises(ValueError):
            save_truth(self.db, catalog, [row, ('a', 'T', (1, 0, 2, 1))])
        self.assertEqual(self.counts('truth_revisions', 'truth_rows'), (0, 0))
        accepted = save_truth(self.db, catalog, [row, ('z', 'T', (1, 0, 2, 1))])
        saved = get_truth_revision(self.db, accepted)
        self.assertEqual([(row.image_id, row.truth_id) for row in saved.rows], [('a', 'T'), ('z', 'T')])

    def test_v2_immutable_revision(self):
        catalog = self.images()
        left = save_truth(self.db, catalog, [('a', 'T', (0, 0, 1, 1))])
        right = save_truth(self.db, catalog, [('a', 'T', (2, 0, 3, 1))])
        self.assertNotEqual(left, right)
        self.assertEqual(get_truth_revision(self.db, left).rows[0].rectangle, Rectangle(0, 0, 1, 1))
        self.assertEqual(get_truth_revision(self.db, right).rows[0].rectangle, Rectangle(2, 0, 3, 1))
        self.assertEqual(self.counts('truth_revisions', 'truth_rows'), (2, 2))

    def test_v3_duplicate_prediction_rejects_entire_submission(self):
        catalog = self.images()
        with self.assertRaises(ValueError):
            save_predictions(self.db, catalog, 'duplicate', [
                ('same', 'a', (0, 0, 1, 1), 1), ('same', 'z', (0, 0, 1, 1), 0),
            ])
        self.assertEqual(self.counts('prediction_revisions', 'prediction_rows'), (0, 0))

    def test_v3_score_roundtrip(self):
        catalog = self.images()
        rows = [('z', 'a', (0, 0, 1, 1), '1/3'), ('a', 'z', (0, 0, 1, 1), Fraction(2, 3))]
        accepted = save_predictions(self.db, catalog, 'vendor', rows)
        self.reopen()
        original = get_prediction_revision(self.db, accepted)
        self.assertEqual([row.score for row in original.rows], [Fraction(1, 3), Fraction(2, 3)])
        for invalid in ['none', '1/0', float('inf'), float('nan')]:
            with self.subTest(score=invalid):
                with self.assertRaises(ValueError):
                    save_predictions(self.db, catalog, 'vendor', [rows[0], ('p', 'z', (0, 0, 1, 1), invalid)])
                self.assertEqual(self.counts('prediction_revisions', 'prediction_rows'), (1, 2))
        self.assertEqual(get_prediction_revision(self.db, accepted), original)

    def test_v3_empty_submission(self):
        catalog = self.images()
        revision_id = save_predictions(self.db, catalog, 'empty', [])
        revision = get_prediction_revision(self.db, revision_id)
        self.assertEqual((revision.revision_id, revision.catalog_id, revision.submission_name, revision.rows),
                         (revision_id, catalog, 'empty', ()))
        self.assertEqual(self.counts('prediction_revisions', 'prediction_rows'), (1, 0))

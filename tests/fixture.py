import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ledger import Image, freeze_task, open_ledger, put_images, save_predictions, save_truth


class LedgerCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory(prefix='strip-ledger-test-')
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'ledger.sqlite3'
        self.db = open_ledger(self.path)
        self.addCleanup(self.db.close)

    def reopen(self) -> None:
        self.db.close()
        self.db = open_ledger(self.path)
        self.addCleanup(self.db.close)

    def images(self) -> int:
        return put_images(self.db, 'shift-one', [Image('z', 4, 4), Image('a', 4, 4)])

    def prepare_task(self, truth, predictions, threshold='1/2') -> int:
        catalog = self.images()
        annotation = save_truth(self.db, catalog, truth)
        submission = save_predictions(self.db, catalog, 'vendor', predictions)
        return freeze_task(self.db, annotation, submission, threshold)

    def counts(self, *tables: str) -> tuple[int, ...]:
        return tuple(self.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables)

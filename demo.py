import json
from contextlib import closing
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from ledger import Image, freeze_task, issue_report, open_ledger, put_images, read_report
from ledger import save_predictions, save_truth


def main() -> None:
    sample_path = Path(__file__).resolve().parent / 'samples' / 'two_images.json'
    sample = json.loads(sample_path.read_text(encoding='utf-8'))
    with TemporaryDirectory(prefix='strip-ledger-demo-') as directory:
        path = Path(directory) / 'inspection.sqlite3'
        with closing(open_ledger(path)) as db:
            catalog = put_images(db, sample['batch_name'], (Image(**row) for row in sample['images']))
            truth = save_truth(db, catalog, sample['truth'])
            submitted = save_predictions(db, catalog, sample['submission_name'], sample['predictions'])
            task = freeze_task(db, truth, submitted, sample['threshold'])
            report_id = issue_report(db, task)
            issued = read_report(db, report_id)
            save_truth(db, catalog, [('a-strip', 'T', (2, 2, 4, 4))])
        with closing(open_ledger(path)) as db:
            received = read_report(db, report_id)

    expected_downstream = {
        'task_id': task,
        'image_misses': [{'image_id': 'a-strip', 'truth_ids': []}, {'image_id': 'z-empty', 'truth_ids': []}],
        'false_positives': [
            {'rank': 1, 'image_id': 'z-empty', 'prediction_id': 'alarm', 'reason': 'no_truth'}
        ],
    }
    actual_downstream = {
        'task_id': received.task_id,
        'image_misses': [
            {'image_id': image.image_id, 'truth_ids': list(image.truth_ids)}
            for image in received.diagnostics.image_misses
        ],
        'false_positives': [asdict(row) for row in received.diagnostics.false_positives],
    }
    if issued.ap != Fraction(1, 2) or issued != received or received.report_id != report_id:
        raise AssertionError(f'unexpected report after reopening: {received!r}')
    if actual_downstream != expected_downstream:
        raise AssertionError(f'unexpected retest evidence: {actual_downstream!r}')
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': 'v7',
        'input': sample,
        'expected': {'ap': '1/2'},
        'actual': {'ap': str(issued.ap)},
        'downstream_expected': expected_downstream,
        'downstream_actual': actual_downstream,
        'code_paths': [
            'tasks/inputs.py', 'matching/ranking.py', 'matching/greedy.py',
            'reports/ap.py', 'reports/diagnostics.py', 'reports/publish.py',
            'reports/store.py', 'reports/read.py',
        ],
        'oracle': '2/3 的空图误报排第一，唯一真值在第二位命中，累计命中 1 除以秩 2，再除以真值数 1。',
    }, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()

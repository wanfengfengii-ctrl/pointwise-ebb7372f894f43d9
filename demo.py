import json
from contextlib import closing
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from ledger import Image, freeze_task, issue_report, issue_tie_mean, open_ledger, put_images
from ledger import read_report, read_tie_mean, save_predictions, save_truth


def run_v1_scenario(sample):
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


TIE_TRUTH_ROWS = (
    ('a', 'A', (0, 0, 2, 2)),
    ('a', 'B', (0, 0, 1, 2)),
)
TIE_PREDICTION_ROWS = (
    ('F', 'a', (0, 0, 2, 2), '1/3'),
    ('N', 'a', (1, 0, 2, 2), '2/6'),
    ('Z', 'z', (0, 0, 1, 1), '3/9'),
)
TIE_THRESHOLD = '1/2'


def run_tie_scenario():
    with TemporaryDirectory(prefix='strip-tie-demo-') as directory:
        path = Path(directory) / 'inspection.sqlite3'
        with closing(open_ledger(path)) as db:
            catalog = put_images(db, 'tie-strip', [Image('a', 4, 4), Image('z', 4, 4)])
            truth = save_truth(db, catalog, TIE_TRUTH_ROWS)
            submitted = save_predictions(db, catalog, 'vendor', TIE_PREDICTION_ROWS)
            task = freeze_task(db, truth, submitted, TIE_THRESHOLD)
            report_id = issue_tie_mean(db, task)
            issued = read_tie_mean(db, report_id)
            # Same three identities, only the stored input row order changes.
            reordered = save_predictions(db, catalog, 'vendor', reversed(TIE_PREDICTION_ROWS))
            other_task = freeze_task(db, truth, reordered, TIE_THRESHOLD)
            other = read_tie_mean(db, issue_tie_mean(db, other_task))
            v1 = read_report(db, issue_report(db, task))
            # A correction adds truth C on the empty image after issuance.
            save_truth(db, catalog, [*TIE_TRUTH_ROWS, ('z', 'C', (0, 0, 1, 1))])
        with closing(open_ledger(path)) as db:
            received = read_tie_mean(db, report_id)
            reopened = read_report(db, issue_report(db, task))

    expected_ap = Fraction(11, 18)
    if issued.ap != expected_ap or other.ap != expected_ap:
        raise AssertionError(f'unexpected tie mean: {issued.ap!r} vs {other.ap!r}')
    if v1.ap != Fraction(1, 2):
        raise AssertionError(f'V1 report changed: {v1.ap!r}')
    if (received.report_id, received.task_id, received.metric, received.ap) != (
        report_id, task, 'tie_mean_ap', expected_ap
    ):
        raise AssertionError(f'unexpected receipt after reopening: {received!r}')
    if reopened.ap != Fraction(1, 2):
        raise AssertionError(f'V1 report changed after reopening: {reopened.ap!r}')
    print('TIE_MEAN_SCENARIO ' + json.dumps({
        'case_id': 'tie-3',
        'input': {'truth': TIE_TRUTH_ROWS, 'predictions': TIE_PREDICTION_ROWS, 'threshold': TIE_THRESHOLD},
        'expected': {'tie_mean_ap': '11/18', 'v1_ap': '1/2'},
        'actual': {
            'tie_mean_ap': str(issued.ap),
            'reordered_tie_mean_ap': str(other.ap),
            'v1_ap': str(v1.ap),
            'received_after_reopen': {
                'report_id': received.report_id,
                'task_id': received.task_id,
                'metric': received.metric,
                'ap': str(received.ap),
            },
        },
        'code_paths': [
            'matching/tie.py', 'reports/tie_publish.py', 'reports/tie_store.py',
            'reports/tie_read.py', 'ledger.py',
        ],
        'handoff': (
            '匹配：高分段落按 V1 逐图占用真值并记录累计命中；每个最低分排列从同一份高分状态继续，'
            '每条记录带 rank 与该序的累计命中，报告无需回看其他序。'
            '报告：按实际全局秩 R 累加 累计命中/R，逐序得到非插值 AP 后取精确 Fraction 均值。'
        ),
    }, ensure_ascii=False, sort_keys=True))


def main() -> None:
    sample_path = Path(__file__).resolve().parent / 'samples' / 'two_images.json'
    sample = json.loads(sample_path.read_text(encoding='utf-8'))
    run_v1_scenario(sample)
    run_tie_scenario()


if __name__ == '__main__':
    main()

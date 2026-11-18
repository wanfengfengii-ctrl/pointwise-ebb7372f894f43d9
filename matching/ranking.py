from collections.abc import Iterable

from submissions.rows import PredictionRow


def rank_predictions(rows: Iterable[PredictionRow]) -> tuple[PredictionRow, ...]:
    return tuple(sorted(rows, key=lambda row: (-row.score, row.prediction_id)))

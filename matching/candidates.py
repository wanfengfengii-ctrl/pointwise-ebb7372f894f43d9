from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from catalog.truth import TruthRow
from matching.iou import iou
from submissions.rows import PredictionRow


@dataclass(frozen=True, slots=True)
class Candidate:
    truth_id: str
    iou: Fraction


def group_truth_by_image(rows: Iterable[TruthRow]) -> dict[str, tuple[TruthRow, ...]]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row.image_id].append(row)
    return {image_id: tuple(truths) for image_id, truths in grouped.items()}


def eligible_candidates(
    prediction: PredictionRow, same_image_truths: Iterable[TruthRow], threshold: Fraction
) -> tuple[Candidate, ...]:
    candidates = []
    for truth in same_image_truths:
        overlap = iou(prediction.rectangle, truth.rectangle)
        if overlap >= threshold:
            candidates.append(Candidate(truth.truth_id, overlap))
    return tuple(candidates)

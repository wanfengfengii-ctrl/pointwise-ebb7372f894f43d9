from collections import defaultdict
from fractions import Fraction

from catalog.truth import TruthRow
from matching.candidates import eligible_candidates, group_truth_by_image
from matching.ranking import rank_predictions
from matching.trace import MatchTrace, MissReason, TraceEntry
from submissions.rows import PredictionRow
from tasks.inputs import TaskInputs


def _match_prediction(
    rank: int,
    prediction: PredictionRow,
    truths: tuple[TruthRow, ...],
    threshold: Fraction,
    occupied: set[str],
) -> TraceEntry:
    if not truths:
        return TraceEntry(rank, prediction.image_id, prediction.prediction_id, miss_reason=MissReason.NO_TRUTH)
    candidates = eligible_candidates(prediction, truths, threshold)
    available = (candidate for candidate in candidates if candidate.truth_id not in occupied)
    best = min(available, key=lambda candidate: (-candidate.iou, candidate.truth_id), default=None)
    if best is None:
        reason = MissReason.OCCUPIED if candidates else MissReason.BELOW_THRESHOLD
        return TraceEntry(rank, prediction.image_id, prediction.prediction_id, miss_reason=reason)
    occupied.add(best.truth_id)
    return TraceEntry(rank, prediction.image_id, prediction.prediction_id, truth_id=best.truth_id)


def build_trace(inputs: TaskInputs) -> MatchTrace:
    by_image = group_truth_by_image(inputs.truth.rows)
    occupied = defaultdict(set)
    ranked = rank_predictions(inputs.predictions.rows)
    entries = []
    for rank, prediction in enumerate(ranked, 1):
        image_id = prediction.image_id
        entries.append(_match_prediction(
            rank, prediction, by_image.get(image_id, ()), inputs.task.threshold, occupied[image_id]
        ))
    return MatchTrace(inputs.task.task_id, tuple(entries))

from collections import defaultdict

from matching.trace import MatchTrace
from reports.model import FalsePositive, ImageMisses, ReportDiagnostics
from tasks.inputs import TaskInputs


def build_diagnostics(inputs: TaskInputs, trace: MatchTrace) -> ReportDiagnostics:
    matched = trace.matched_truth_keys()
    missed = defaultdict(list)
    for truth in inputs.truth.rows:
        if (truth.image_id, truth.truth_id) not in matched:
            missed[truth.image_id].append(truth.truth_id)
    image_misses = tuple(
        ImageMisses(image.image_id, tuple(sorted(missed[image.image_id])))
        for image in sorted(inputs.catalog.images, key=lambda image: image.image_id)
    )
    false_positives = tuple(
        FalsePositive(entry.rank, entry.image_id, entry.prediction_id, entry.miss_reason.value)
        for entry in trace.entries if entry.miss_reason is not None
    )
    return ReportDiagnostics(image_misses, false_positives)

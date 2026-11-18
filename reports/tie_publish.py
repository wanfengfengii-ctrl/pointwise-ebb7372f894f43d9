import sqlite3

from matching.tie import mean_average_precision, split_lowest_scores
from reports.tie_store import insert_tie_mean_report
from tasks.inputs import TaskInputs, load_task_inputs

MAX_IMAGES = 32
MAX_LOWEST_PER_IMAGE = 4


def check_tie_limits(inputs: TaskInputs) -> None:
    """Reject batches outside the documented lowest-group-reporting envelope."""

    if len(inputs.catalog.images) > MAX_IMAGES:
        raise ValueError(
            f'tie mean reporting covers at most {MAX_IMAGES} catalog images,'
            f' got {len(inputs.catalog.images)}'
        )
    _, lowest = split_lowest_scores(inputs.predictions.rows)
    per_image: dict[str, int] = {}
    for prediction in lowest:
        per_image[prediction.image_id] = per_image.get(prediction.image_id, 0) + 1
    for image_id, count in per_image.items():
        if count > MAX_LOWEST_PER_IMAGE:
            raise ValueError(
                f'tie mean reporting allows at most {MAX_LOWEST_PER_IMAGE} lowest-group'
                f' predictions per image, got {count} in {image_id!r}'
            )


def issue_tie_mean(db: sqlite3.Connection, task_id: int) -> int:
    inputs = load_task_inputs(db, task_id)
    check_tie_limits(inputs)
    ap = mean_average_precision(inputs, len(inputs.truth.rows))
    return insert_tie_mean_report(db, task_id, ap)

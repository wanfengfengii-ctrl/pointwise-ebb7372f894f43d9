from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True, slots=True)
class TieMeanSnapshot:
    """A frozen lowest-score-group mean AP report."""

    report_id: int
    task_id: int
    metric: str
    ap: Fraction

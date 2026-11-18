from dataclasses import dataclass
from enum import StrEnum


class MissReason(StrEnum):
    NO_TRUTH = 'no_truth'
    BELOW_THRESHOLD = 'below_threshold'
    OCCUPIED = 'occupied'


@dataclass(frozen=True, slots=True)
class TraceEntry:
    rank: int
    image_id: str
    prediction_id: str
    truth_id: str | None = None
    miss_reason: MissReason | None = None


@dataclass(frozen=True, slots=True)
class MatchTrace:
    task_id: int
    entries: tuple[TraceEntry, ...]

    def matched_truth_keys(self) -> frozenset[tuple[str, str]]:
        return frozenset(
            (entry.image_id, entry.truth_id) for entry in self.entries if entry.truth_id is not None
        )

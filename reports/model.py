from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True, slots=True)
class FalsePositive:
    rank: int
    image_id: str
    prediction_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class ImageMisses:
    image_id: str
    truth_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReportDiagnostics:
    image_misses: tuple[ImageMisses, ...]
    false_positives: tuple[FalsePositive, ...]


@dataclass(frozen=True, slots=True)
class ReportSnapshot:
    report_id: int
    task_id: int
    ap: Fraction
    diagnostics: ReportDiagnostics

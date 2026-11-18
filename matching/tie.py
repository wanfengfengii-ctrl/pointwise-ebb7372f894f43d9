from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from itertools import permutations
from math import comb, factorial

from matching.candidates import group_truth_by_image
from matching.greedy import _match_prediction
from matching.ranking import rank_predictions
from matching.trace import MissReason
from submissions.rows import PredictionRow
from tasks.inputs import TaskInputs


@dataclass(frozen=True, slots=True)
class TieOrderEntry:
    """One position of a concrete full ordering.

    ``cumulative_hits`` is the number of hits at or before this position,
    counted from the first position of the order. It is the handoff evidence:
    a scorer reading this entry alone can attribute ``cumulative_hits / rank``
    to a hit at the actual global ``rank``. The fixed high-score entries carry
    the same handoff, so a lowest-group ordering continues their hit count
    without re-deriving it.
    """

    rank: int
    image_id: str
    prediction_id: str
    truth_id: str | None
    miss_reason: MissReason | None
    cumulative_hits: int


@dataclass(frozen=True, slots=True)
class TieOrderTrace:
    task_id: int
    entries: tuple[TieOrderEntry, ...]

    def matched_truth_keys(self) -> frozenset[tuple[str, str]]:
        return frozenset(
            (entry.image_id, entry.truth_id) for entry in self.entries if entry.truth_id is not None
        )


@dataclass(frozen=True, slots=True)
class HighSegment:
    """The fixed V1-ordered score positions above the lowest-score group.

    Every lowest-group ordering starts from these entries: the same global
    ranks, the same cumulative hits and the same per-image truth occupancy.
    """

    entries: tuple[TieOrderEntry, ...]
    occupied: dict[str, frozenset[str]]
    hits: int

    @property
    def size(self) -> int:
        return len(self.entries)


@dataclass(frozen=True, slots=True)
class TieStatistics:
    """Exact aggregates over all equally likely lowest-group orderings.

    For one order let ``H`` be the hit count of the fixed higher segment, let
    ``x`` range over lowest-group hits, let ``p(x)`` be the position of ``x``
    inside the group and ``R(x) = high.size + p(x)`` its actual global rank.
    That order's non-interpolated precision sum is

        high_terms + sum_x (H + 1 + #{lowest hits before x}) / R(x)

    ``high_terms`` is identical for every order. Averaging term by term over
    all orders splits the rest into three aggregates:

    * ``own``   = E[sum_x 1/R(x)]                           (each hit alone)
    * ``same``  = E[sum_{y before x, same image, both hit} 1/R(x)]
    * ``cross`` = E[sum_{y before x, other images, both hit} 1/R(x)]

    ``same`` reads the joint local order of one image; ``cross`` couples two
    images only through their local ranks, because the interleaving of image
    slots is uniform and independent of the local orders.
    """

    high: HighSegment
    high_terms: Fraction
    lowest_count: int
    own: Fraction
    same: Fraction
    cross: Fraction


def split_lowest_scores(
    rows: Iterable[PredictionRow],
) -> tuple[tuple[PredictionRow, ...], tuple[PredictionRow, ...]]:
    """Split the V1 ranking into the higher segment and the lowest group.

    The split uses the whole-batch minimum score. Scores are exact rationals,
    so ``1/3`` and ``2/6`` meet in the same group. Identity is the prediction
    ID: the group is a set of identities, and the mean weighs every ordering
    of it equally.
    """

    ranked = rank_predictions(rows)
    if not ranked:
        return (), ()
    lowest = ranked[-1].score
    boundary = len(ranked)
    while boundary and ranked[boundary - 1].score == lowest:
        boundary -= 1
    return ranked[:boundary], ranked[boundary:]


def build_high_segment(inputs: TaskInputs, higher: tuple[PredictionRow, ...]) -> HighSegment:
    """Match the higher segment with the V1 greedy and freeze its state."""

    by_image = group_truth_by_image(inputs.truth.rows)
    occupied: defaultdict[str, set[str]] = defaultdict(set)
    entries = []
    hits = 0
    for rank, prediction in enumerate(higher, 1):
        image_id = prediction.image_id
        entry = _match_prediction(
            rank,
            prediction,
            by_image.get(image_id, ()),
            inputs.task.threshold,
            occupied[image_id],
        )
        if entry.truth_id is not None:
            hits += 1
        entries.append(_handoff(entry, hits))
    return HighSegment(
        tuple(entries),
        {image_id: frozenset(truths) for image_id, truths in occupied.items()},
        hits,
    )


def continue_order(
    inputs: TaskInputs, high: HighSegment, lowest: Iterable[PredictionRow]
) -> TieOrderTrace:
    """Continue one concrete lowest-group ordering from the inherited state."""

    by_image = group_truth_by_image(inputs.truth.rows)
    occupied: defaultdict[str, set[str]] = defaultdict(set)
    for image_id, truth_ids in high.occupied.items():
        occupied[image_id].update(truth_ids)
    entries = list(high.entries)
    hits = high.hits
    rank = high.size
    for prediction in lowest:
        rank += 1
        entry = _match_prediction(
            rank,
            prediction,
            by_image.get(prediction.image_id, ()),
            inputs.task.threshold,
            occupied[prediction.image_id],
        )
        if entry.truth_id is not None:
            hits += 1
        entries.append(_handoff(entry, hits))
    return TieOrderTrace(inputs.task.task_id, tuple(entries))


def _handoff(entry, cumulative_hits: int) -> TieOrderEntry:
    return TieOrderEntry(
        entry.rank,
        entry.image_id,
        entry.prediction_id,
        entry.truth_id,
        entry.miss_reason,
        cumulative_hits,
    )


@lru_cache(maxsize=None)
def _position_share(k: int, m: int, local_rank: int, position: int) -> Fraction:
    """P(this item is globally at ``position`` | local rank in an m-item image).

    Given the local rank, the item's position is the rank-th smallest element
    of its image's uniformly chosen m-subset of the k slots.
    """

    if not (1 <= local_rank <= m) or not (1 <= position <= k):
        return Fraction(0)
    return Fraction(
        comb(position - 1, local_rank - 1) * comb(k - position, m - local_rank),
        comb(k, m),
    )


@lru_cache(maxsize=None)
def _before_share(
    k: int, m_own: int, own_rank: int, m_other: int, other_rank: int, position: int
) -> Fraction:
    """P(other image's rank-``other_rank`` item lies before ``position``).

    Conditional on this image's ``own_rank`` item being at ``position``, the
    own image uses ``own_rank - 1`` of the earlier slots, leaving a uniform
    ``m_other``-subset of the other slots for the other image.
    """

    if not (1 <= own_rank <= m_own) or not (1 <= other_rank <= m_other):
        return Fraction(0)
    if not (1 <= position <= k):
        return Fraction(0)
    before = position - own_rank
    after = (k - position) - (m_own - own_rank)
    remaining = k - m_own
    if remaining <= 0 or before < 0 or after < 0:
        return Fraction(0)
    total = comb(remaining, m_other)
    if total == 0:
        return Fraction(0)
    count = sum(
        comb(before, taken) * comb(after, m_other - taken)
        for taken in range(other_rank, min(m_other, before) + 1)
        if m_other - taken <= after
    )
    return Fraction(count, total)


def _local_hits(
    inputs: TaskInputs,
    high: HighSegment,
    image_id: str,
    order: tuple[PredictionRow, ...],
    truths,
) -> tuple[bool, ...]:
    """Run the V1 greedy over one local order sharing the inherited occupancy."""

    occupied = set(high.occupied.get(image_id, ()))
    flags = []
    for prediction in order:
        entry = _match_prediction(1, prediction, truths, inputs.task.threshold, occupied)
        flags.append(entry.truth_id is not None)
    return tuple(flags)


@dataclass(frozen=True, slots=True)
class _LocalProfile:
    """Exact description of one image's lowest-group items under the V1 greedy.

    Averaged over the uniform local orders:

    * ``hit[r]`` is P(the item at local rank r matches a truth);
    * ``earlier[r]`` is E[1_{rank r hits} * (# earlier hits in this image)].
    """

    rows: tuple[PredictionRow, ...]
    hit: tuple[Fraction, ...]
    earlier: tuple[Fraction, ...]


def _local_profile(
    inputs: TaskInputs, high: HighSegment, image_id: str, rows: tuple[PredictionRow, ...]
) -> _LocalProfile:
    m = len(rows)
    truths = group_truth_by_image(inputs.truth.rows).get(image_id, ())
    weight = Fraction(1, factorial(m))
    hit = [Fraction(0)] * (m + 1)
    earlier = [Fraction(0)] * (m + 1)
    orderings = tuple(permutations(rows)) if m > 1 else (rows,)
    for order in orderings:
        flags = _local_hits(inputs, high, image_id, order, truths)
        before = 0
        for rank, flag in enumerate(flags, 1):
            if flag:
                hit[rank] += weight
                earlier[rank] += weight * before
                before += 1
    return _LocalProfile(rows, tuple(hit), tuple(earlier))


def tie_statistics(inputs: TaskInputs) -> TieStatistics:
    higher, lowest = split_lowest_scores(inputs.predictions.rows)
    high = build_high_segment(inputs, higher)
    high_terms = Fraction(0)
    for entry in high.entries:
        if entry.truth_id is not None:
            high_terms += Fraction(entry.cumulative_hits, entry.rank)

    k = len(lowest)
    if k == 0:
        return TieStatistics(high, high_terms, 0, Fraction(0), Fraction(0), Fraction(0))

    grouped: defaultdict[str, list[PredictionRow]] = defaultdict(list)
    for prediction in lowest:
        grouped[prediction.image_id].append(prediction)
    profiles = [
        _local_profile(inputs, high, image_id, tuple(rows))
        for image_id, rows in grouped.items()
    ]

    own_total = Fraction(0)
    same_total = Fraction(0)
    for profile in profiles:
        m = len(profile.rows)
        for rank in range(1, m + 1):
            if not profile.hit[rank]:
                continue
            for position in range(1, k + 1):
                share = _position_share(k, m, rank, position)
                if not share:
                    continue
                weight = share / (high.size + position)
                own_total += profile.hit[rank] * weight
                same_total += profile.earlier[rank] * weight

    # Pairwise walk: ``x`` may be any lowest-group hit at ``position``; every
    # other image contributes its expected hits before that position. The
    # local rank of ``x`` is fixed by the profile entry, so the rank
    # conditioning of both sides stays exact.
    cross_total = Fraction(0)
    for profile in profiles:
        m_own = len(profile.rows)
        for own_rank in range(1, m_own + 1):
            if not profile.hit[own_rank]:
                continue
            for position in range(1, k + 1):
                share = _position_share(k, m_own, own_rank, position)
                if not share:
                    continue
                outside = Fraction(0)
                for other in profiles:
                    if other is profile:
                        continue
                    m_other = len(other.rows)
                    outside += sum(
                        other.hit[rank]
                        * _before_share(k, m_own, own_rank, m_other, rank, position)
                        for rank in range(1, m_other + 1)
                    )
                cross_total += (
                    profile.hit[own_rank] * share * outside / (high.size + position)
                )
    return TieStatistics(high, high_terms, k, own_total, same_total, cross_total)


def mean_average_precision(inputs: TaskInputs, truth_count: int) -> Fraction:
    """Exact mean over all equally likely lowest-group orderings of V1 AP."""

    if truth_count <= 0:
        raise ValueError('average precision requires a positive truth count')
    stats = tie_statistics(inputs)
    total = (
        stats.high_terms
        + (stats.high.hits + 1) * stats.own
        + stats.same
        + stats.cross
    )
    return total / truth_count

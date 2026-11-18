from fractions import Fraction

from matching.trace import MatchTrace


def average_precision(trace: MatchTrace, truth_count: int) -> Fraction:
    if truth_count <= 0:
        raise ValueError('average precision requires a positive truth count')
    hits = 0
    precision_sum = Fraction(0)
    for entry in trace.entries:
        if entry.truth_id is not None:
            hits += 1
            precision_sum += Fraction(hits, entry.rank)
    return precision_sum / truth_count

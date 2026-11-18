from fractions import Fraction


def parse_score(value: object) -> Fraction:
    if isinstance(value, bool):
        raise ValueError('a confidence score must be rational')
    try:
        return Fraction(value)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        raise ValueError('a confidence score must be rational') from exc

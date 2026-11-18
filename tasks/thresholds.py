from fractions import Fraction


def parse_iou_threshold(value: object) -> Fraction:
    if isinstance(value, bool):
        raise ValueError('IoU threshold must be rational and in (0, 1]')
    try:
        threshold = Fraction(value)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        raise ValueError('IoU threshold must be rational and in (0, 1]') from exc
    if not 0 < threshold <= 1:
        raise ValueError('IoU threshold must be in (0, 1]')
    return threshold

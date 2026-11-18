from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

RationalInput = int | str | float | Decimal | Fraction


@dataclass(frozen=True, slots=True)
class Rectangle:
    x0: Fraction
    y0: Fraction
    x1: Fraction
    y1: Fraction

    @property
    def area(self) -> Fraction:
        return (self.x1 - self.x0) * (self.y1 - self.y0)


def make_rectangle(coordinates: Iterable[RationalInput], width: int, height: int) -> Rectangle:
    if isinstance(coordinates, (str, bytes)):
        raise ValueError('a rectangle requires four rational coordinates')
    try:
        raw_x0, raw_y0, raw_x1, raw_y1 = coordinates
        values = (raw_x0, raw_y0, raw_x1, raw_y1)
        if any(isinstance(value, bool) for value in values):
            raise ValueError('boolean coordinate')
        x0, y0, x1, y1 = (Fraction(value) for value in values)
    except (TypeError, ValueError, OverflowError, ZeroDivisionError) as exc:
        raise ValueError('a rectangle requires four rational coordinates') from exc
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError('rectangle must have positive area and lie inside the image')
    return Rectangle(x0, y0, x1, y1)


def pack_rectangle(rectangle: Rectangle) -> tuple[str, str, str, str]:
    return (str(rectangle.x0), str(rectangle.y0), str(rectangle.x1), str(rectangle.y1))


def unpack_rectangle(values: Iterable[str]) -> Rectangle:
    return Rectangle(*(Fraction(value) for value in values))

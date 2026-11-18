from fractions import Fraction

from catalog.rectangles import Rectangle


def intersection_area(left: Rectangle, right: Rectangle) -> Fraction:
    width = min(left.x1, right.x1) - max(left.x0, right.x0)
    height = min(left.y1, right.y1) - max(left.y0, right.y0)
    if width <= 0 or height <= 0:
        return Fraction(0)
    return width * height


def iou(left: Rectangle, right: Rectangle) -> Fraction:
    overlap = intersection_area(left, right)
    return overlap / (left.area + right.area - overlap)

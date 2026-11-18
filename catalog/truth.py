from collections.abc import Iterable
from dataclasses import dataclass

from catalog.images import ImageCatalog
from catalog.rectangles import RationalInput, Rectangle, make_rectangle

TruthInput = tuple[str, str, Iterable[RationalInput]]


@dataclass(frozen=True, slots=True)
class TruthRow:
    image_id: str
    truth_id: str
    rectangle: Rectangle


def validate_truth_rows(catalog: ImageCatalog, rows: Iterable[TruthInput]) -> tuple[TruthRow, ...]:
    validated = []
    seen = set()
    for row in rows:
        try:
            image_id, truth_id, coordinates = row
        except (TypeError, ValueError) as exc:
            raise ValueError('expected image ID, truth ID and rectangle') from exc
        if not isinstance(truth_id, str) or not truth_id.strip():
            raise ValueError('a truth ID is required')
        image = catalog.require_image(image_id)
        key = (image.image_id, truth_id)
        if key in seen:
            raise ValueError(f'duplicate truth ID {truth_id!r} in image {image.image_id!r}')
        rectangle = make_rectangle(coordinates, image.width, image.height)
        validated.append(TruthRow(image.image_id, truth_id, rectangle))
        seen.add(key)
    return tuple(validated)

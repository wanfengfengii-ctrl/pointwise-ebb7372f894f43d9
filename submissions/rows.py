from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from catalog.images import ImageCatalog
from catalog.rectangles import RationalInput, Rectangle, make_rectangle
from submissions.scores import parse_score

PredictionInput = tuple[str, str, Iterable[RationalInput], RationalInput]


@dataclass(frozen=True, slots=True)
class PredictionRow:
    prediction_id: str
    image_id: str
    rectangle: Rectangle
    score: Fraction


def validate_prediction_rows(
    catalog: ImageCatalog, rows: Iterable[PredictionInput]
) -> tuple[PredictionRow, ...]:
    validated = []
    seen = set()
    for row in rows:
        try:
            prediction_id, image_id, coordinates, score = row
        except (TypeError, ValueError) as exc:
            raise ValueError('expected prediction ID, image ID, rectangle and score') from exc
        if not isinstance(prediction_id, str) or not prediction_id.strip():
            raise ValueError('a prediction ID is required')
        if prediction_id in seen:
            raise ValueError(f'duplicate prediction ID {prediction_id!r}')
        image = catalog.require_image(image_id)
        rectangle = make_rectangle(coordinates, image.width, image.height)
        validated.append(PredictionRow(prediction_id, image.image_id, rectangle, parse_score(score)))
        seen.add(prediction_id)
    return tuple(validated)

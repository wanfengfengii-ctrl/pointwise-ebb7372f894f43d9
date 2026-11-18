import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Image:
    image_id: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class ImageCatalog:
    catalog_id: int
    batch_name: str
    images: tuple[Image, ...]

    def require_image(self, image_id: str) -> Image:
        for image in self.images:
            if image.image_id == image_id:
                return image
        raise ValueError(f'image {image_id!r} is outside catalog {self.catalog_id}')


def initialize_images(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS image_catalogs (
            id INTEGER PRIMARY KEY,
            batch_name TEXT NOT NULL
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS catalog_images (
            catalog_id INTEGER NOT NULL REFERENCES image_catalogs(id),
            image_id TEXT NOT NULL,
            width INTEGER NOT NULL CHECK (width > 0),
            height INTEGER NOT NULL CHECK (height > 0),
            PRIMARY KEY (catalog_id, image_id)
        )
    ''')


def put_images(db: sqlite3.Connection, batch_name: str, images: Iterable[Image]) -> int:
    if not isinstance(batch_name, str) or not batch_name.strip():
        raise ValueError('a batch name is required')
    rows = tuple(images)
    if not rows:
        raise ValueError('a catalog must contain at least one image')
    seen = set()
    for image in rows:
        if not isinstance(image, Image):
            raise ValueError('expected an Image record')
        if not isinstance(image.image_id, str) or not image.image_id.strip():
            raise ValueError('an image ID is required')
        if any(type(size) is not int or size <= 0 for size in (image.width, image.height)):
            raise ValueError(f'image {image.image_id!r} requires positive integer dimensions')
        if image.image_id in seen:
            raise ValueError(f'duplicate image ID {image.image_id!r}')
        seen.add(image.image_id)

    db.execute('BEGIN IMMEDIATE')
    with db:
        catalog_id = db.execute(
            'INSERT INTO image_catalogs (batch_name) VALUES (?)', (batch_name,)
        ).lastrowid
        db.executemany(
            'INSERT INTO catalog_images VALUES (?, ?, ?, ?)',
            ((catalog_id, image.image_id, image.width, image.height) for image in rows),
        )
    return catalog_id


def get_image_catalog(db: sqlite3.Connection, catalog_id: int) -> ImageCatalog:
    if type(catalog_id) is not int or not 0 < catalog_id < 2**63:
        raise KeyError(catalog_id)
    header = db.execute(
        'SELECT batch_name FROM image_catalogs WHERE id = ?', (catalog_id,)
    ).fetchone()
    if header is None:
        raise KeyError(catalog_id)
    images = db.execute(
        '''SELECT image_id, width, height FROM catalog_images
           WHERE catalog_id = ? ORDER BY image_id''',
        (catalog_id,),
    )
    return ImageCatalog(catalog_id, header[0], tuple(Image(*row) for row in images))

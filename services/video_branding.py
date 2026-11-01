"""Shared, aspect-preserving social branding for Video Studio compositions."""
from functools import lru_cache
from pathlib import Path

from PIL import Image

LOGO = Path(__file__).resolve().parents[1] / 'assets/logo/RH Racing Social Media Overlay.png'
BRANDING_VERSION = 'rh-social-v1'


@lru_cache(maxsize=16)
def _sprite(width, height, modified):
    with Image.open(LOGO) as source:
        image = source.convert('RGBA')
    # Ignore near-transparent export padding, without modifying the source file.
    bounds = image.getchannel('A').point(lambda alpha: 255 if alpha > 32 else 0).getbbox()
    if bounds:
        image = image.crop(bounds)
    image.thumbnail((width, height), Image.Resampling.LANCZOS)
    return image


def add_social_brand(image, portrait_height=84, placement='header'):
    """Reserve the upper-right header, outside cars, cards, map and telemetry."""
    width, height = image.size
    portrait = height > width
    scale = width / (540 if portrait else 960)
    box_width, box_height = (122, portrait_height) if portrait else (138, 84)
    sprite = _sprite(round(box_width * scale), round(box_height * scale), LOGO.stat().st_mtime_ns)
    x = round(width - 28 * scale) - sprite.width
    y = round(8 * scale)
    if placement=='onboard_left':
        x=round(20*scale);y=round(390*scale)
    elif placement=='footer':
        x=round((width-sprite.width)/2)
        y=round(height-(157 if portrait else 129)*scale)
    elif placement=='social_safe' and portrait:
        # Center directly below the second Night Chase telemetry card.
        x=round(86*scale-sprite.width/2)
        y=round(485*scale)
    image.paste(sprite, (x, y), sprite)
    return image

"""Shared EEVEE quality settings, independent of the selected track source."""

RENDER_SAMPLES = {'Fast': 8, 'Balanced': 24, 'High': 64}

# Local RTX 3060 (12 GB): leave resolution/samples untouched, give EEVEE's
# virtual shadow atlas sufficient room instead of dropping shadow pages.
SHADOW_POOL_SIZE = '1024'


def render_samples(quality):
    return RENDER_SAMPLES[quality]

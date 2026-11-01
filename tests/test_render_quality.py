import unittest

from services.render_quality import render_samples,SHADOW_POOL_SIZE


class RenderQualityTests(unittest.TestCase):
    def test_shadow_pool_preserves_detail_with_more_memory(self):
        self.assertEqual(SHADOW_POOL_SIZE,'1024')
    def test_fast_has_usable_antialiasing_and_quality_scales(self):
        self.assertEqual([render_samples(q) for q in ('Fast', 'Balanced', 'High')],
                         [8, 24, 64])

    def test_unknown_quality_is_not_silently_downgraded(self):
        with self.assertRaises(KeyError):
            render_samples('Unknown')

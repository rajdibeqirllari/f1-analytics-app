import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from services.ghost_material import configure_ghost_material


class GhostMaterialTests(unittest.TestCase):
    def test_front_surface_only_preserves_ghost_alpha(self):
        alpha=SimpleNamespace(default_value=1.)
        nodes=MagicMock()
        nodes.get.return_value=SimpleNamespace(inputs={'Alpha':alpha})
        fade=SimpleNamespace(inputs={k:SimpleNamespace(default_value=None) for k in
            ('From Min','From Max','To Min','To Max','Value')},outputs={'Result':object()})
        nodes.new.side_effect=[SimpleNamespace(outputs={'View Distance':object()}),fade]
        mat=SimpleNamespace(node_tree=SimpleNamespace(nodes=nodes,links=MagicMock()))
        configure_ghost_material(mat)
        self.assertEqual(alpha.default_value,.42)
        self.assertEqual(mat.surface_render_method,'BLENDED')
        self.assertFalse(mat.use_transparency_overlap)
        self.assertEqual(nodes.new.call_count,2)
        self.assertEqual(mat.node_tree.links.new.call_count,2)
        self.assertEqual(fade.inputs['From Min'].default_value,.30)
        self.assertEqual(fade.inputs['From Max'].default_value,2.5)

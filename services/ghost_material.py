"""Stable single-shell transparency for illustrative comparison cars."""


def configure_ghost_material(material, alpha=.42):
    material.node_tree.nodes.get('Principled BSDF').inputs['Alpha'].default_value=alpha
    material.surface_render_method='BLENDED'
    # Rendering every inner/back shell makes blended bodywork sort against
    # itself as the ghost intersects the camera car. Keep its front surface.
    material.use_transparency_overlap=False
    # A rival can physically pass through the onboard camera. Fade only those
    # fragments close to the lens instead of abruptly chopping them at clip_start.
    nodes=material.node_tree.nodes;links=material.node_tree.links
    camera=nodes.new('ShaderNodeCameraData')
    fade=nodes.new('ShaderNodeMapRange');fade.name='Ghost near-camera fade'
    fade.clamp=True;fade.interpolation_type='SMOOTHSTEP'
    fade.inputs['From Min'].default_value=.30
    fade.inputs['From Max'].default_value=2.5
    fade.inputs['To Min'].default_value=0.
    fade.inputs['To Max'].default_value=alpha
    links.new(camera.outputs['View Distance'],fade.inputs['Value'])
    links.new(fade.outputs['Result'],nodes.get('Principled BSDF').inputs['Alpha'])

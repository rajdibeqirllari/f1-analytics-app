import bpy
for p in bpy.context.scene.eevee.bl_rna.properties:
    if 'shadow' in p.identifier:
        value=getattr(bpy.context.scene.eevee,p.identifier)
        print('SHADOW_SETTING',p.identifier,str(value),
              [(e.identifier,e.name) for e in p.enum_items] if p.type=='ENUM' else '')

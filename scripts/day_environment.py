"""Original batched scenery for telemetry-built daytime circuits (Blender only)."""
import math
import bpy
import numpy as np
from mathutils.kdtree import KDTree


def build_environment(plan, material, scene, ground, road):
    profile=plan['profile']
    points=np.asarray(plan['points']);normals=np.asarray(plan['normals'])
    distances=np.asarray(plan['distances']);half=plan['road_half']
    heights=np.asarray(plan.get('heights',np.zeros(len(points))))
    grades=np.gradient(heights,np.maximum.accumulate(distances+np.arange(len(distances))*1e-8))
    # World-space noise: variation is measured in metres, not stretched over
    # the giant horizon plane. Modest bump adds surface grain without geometry.
    terrain=material('Natural terrain · '+profile['kind'],profile['ground'],rough=1)
    nodes=terrain.node_tree.nodes;links=terrain.node_tree.links
    coord=nodes.new('ShaderNodeTexCoord')
    noise=nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=.045;noise.inputs['Detail'].default_value=2
    links.new(coord.outputs['Object'],noise.inputs['Vector'])
    ramp=nodes.new('ShaderNodeValToRGB')
    for item,factor in zip(ramp.color_ramp.elements,(.65,1.25)):
        item.color=(*(min(1,c*factor) for c in profile['ground']),1)
    links.new(noise.outputs['Fac'],ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'],nodes.get('Principled BSDF').inputs['Base Color'])
    ground.data.materials.clear();ground.data.materials.append(terrain)
    # Fine asphalt grain. No expensive displacement, imported textures or extra lights.
    asphalt=road.data.materials[0];shader=asphalt.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=(.055,.060,.065,1)
    grain=asphalt.node_tree.nodes.new('ShaderNodeTexNoise');grain.inputs['Scale'].default_value=120
    bump=asphalt.node_tree.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=.008
    asphalt.node_tree.links.new(grain.outputs['Fac'],bump.inputs['Height'])
    asphalt.node_tree.links.new(bump.outputs['Normal'],shader.inputs['Normal'])
    materials=[material('Weathered concrete',(.56,.56,.50),rough=.9),
        material('Armco galvanized steel',(.32,.35,.35),metallic=.55,rough=.65),
        material('Fence and grandstand steel',(.12,.15,.16),metallic=.45,rough=.65),
        material('Shoulder and gravel',profile['runoff'],rough=1),
        material('Tree bark',(.10,.075,.043),rough=1),
        material('Foliage shadow',(.055,.09,.027),rough=1),
        material('Foliage midtone',(.10,.16,.045),rough=1),
        material('Foliage sunlit',(.16,.21,.065),rough=1),
        material('Grandstand seating',(.12,.20,.25),rough=.8),
        material('Grandstand roof',(.57,.59,.55),metallic=.25,rough=.7),
        material('Distant architecture',(.32,.36,.38),rough=.85),
        material('Lake water',(.055,.16,.18),metallic=.25,rough=.28),
        material('Weathered track edge paint',(.68,.69,.61),rough=.85)]
    vertices=[];faces=[];indices=[]
    def box(center,size,angle,index,grade=0.):
        a=np.array([math.cos(angle),math.sin(angle),grade]);b=np.array([-a[1],a[0],0]);center=np.array(center)
        start=len(vertices)
        for z in (-1,1):
            for y,x in ((-1,-1),(-1,1),(1,1),(1,-1)):
                vertices.append((center+a*x*size[0]/2+b*y*size[1]/2+[0,0,z*size[2]/2]).tolist())
        for face in ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)):
            faces.append(tuple(start+i for i in face));indices.append(index)
    def ribbon(left,right,z,index):
        start=len(vertices)
        for a,b,h in zip(left,right,heights):vertices.extend([[*a,z+h],[*b,z+h]])
        for i in range(len(left)-1):faces.append((start+2*i,start+2*i+2,start+2*i+3,start+2*i+1));indices.append(index)
    tree=KDTree(len(points))
    for i,q in enumerate(points):tree.insert((*q,0),i)
    tree.balance()
    # Narrow shoulders connect kerbs to terrain; rails and catch-fence establish
    # scale and contact with the landscape instead of a floating asphalt strip.
    for sign in (-1,1):
        ribbon(points+normals*sign*(half-.18),points+normals*sign*(half-.04),.025,12)
        inner=points+normals*sign*(half+.9)
        outer=points+normals*sign*(half+2.5)
        ribbon(inner,outer,-.008,3)
        for i in np.searchsorted(distances,np.arange(0,distances[-1]-9,8.)):
            angle=math.atan2(normals[i,0],-normals[i,1])
            q=points[i]+normals[i]*sign*(half+4.2)
            if tree.find((*q,0))[2]<half+3.5:continue
            if profile['kind'] in ('parkland','city','coastal'):
                box([*q,.48+heights[i]],(8.,.42,1.),angle,0,grades[i])
            else:
                for z in (.4,.66,.92):box([*q,z+heights[i]],(8.,.14,.17),angle,1,grades[i])
            box([*q,1.65+heights[i]],(.09,.09,3.3),angle,2)
            for z in (1.25,2.0,2.75,3.3):box([*q,z+heights[i]],(8.,.018,.018),angle,2,grades[i])
    for item in plan['trees']:
        x,y=item['center'];h=item['height'];r=item['radius']
        base_z=item.get('base_z',0.)
        box([x,y,base_z+h*.28],(.32,.32,h*.56),0,4)
        # Irregular rounded crowns: all trees batched into one mesh, no particles.
        for factor,z in ((1.,h*.65),(.75,h*.85)):
            z+=base_z
            base=len(vertices)
            vertices.extend([[x,y,z-h*.24],[x+r*.12,y,z+h*.27]])
            for ring,(rz,rf) in enumerate(((-.13,.65),(.015,1.),(.16,.65))):
                for j in range(8):
                    angle=j*math.pi/4+ring*.19
                    radius=r*factor*rf*(1+.12*math.sin(j*2.3+x))
                    vertices.append([x+radius*math.cos(angle),y+radius*math.sin(angle),z+h*rz])
            for j in range(8):
                k=(j+1)%8
                for face in ((0,2+k,2+j),(1,18+j,18+k),(2+j,2+k,10+k,10+j),(10+j,10+k,18+k,18+j)):
                    faces.append(tuple(base+n for n in face));indices.append(5+item['tone'])
    for item in plan['structures']:
        x,y=item['center'];angle=item['heading']
        base_z=item.get('base_z',0.)
        if 'foundation_bottom_z' in item:
            bottom=item['foundation_bottom_z'];top=base_z+.05
            width=item.get('width',30.);depth=width*.7 if item['kind']=='building' else 9.
            if top>bottom:
                box([x,y,(bottom+top)/2],(width,depth,top-bottom),angle,0)
        if item['kind']=='building':
            h=item['height'];w=item['width']
            box([x,y,base_z+h/2],(w,w*.7,h),angle,10)
            # Horizontal facade bands supply depth without lit windows in daytime.
            for z in np.arange(5,h,5):box([x,y,base_z+z],(w+.12,w*.7+.12,.2),angle,9)
        else:
            b=np.array([-math.sin(angle),math.cos(angle)])
            for row in range(7):
                q=np.array([x,y])+b*(row-3)*1.25
                box([*q,base_z+.5+row*.45],(30,1.2,1+row*.9),angle,8)
            box([x,y,base_z+8],(34,12,.35),angle,9)
            for sign in (-1,1):box([x+sign*14*math.cos(angle),y+sign*14*math.sin(angle),base_z+4],(.28,.28,8),angle,2)
    if plan['lake']:
        x,y=plan['lake']['center'];r=plan['lake']['radius'];base=len(vertices)
        water_z=plan['lake'].get('base_z',0.)+.02
        vertices.append([x,y,water_z])
        for angle in np.linspace(0,2*np.pi,65):vertices.append([x+r*math.cos(angle),y+r*math.sin(angle),water_z])
        for i in range(64):faces.append((base,base+i+1,base+i+2));indices.append(11)
    mesh=bpy.data.meshes.new('Batched venue-inspired surroundings');mesh.from_pydata(vertices,[],faces);mesh.update()
    obj=bpy.data.objects.new(mesh.name,mesh);scene.collection.objects.link(obj)
    for mat in materials:mesh.materials.append(mat)
    for face,index in zip(mesh.polygons,indices):
        face.material_index=index
        if 5<=index<=7:face.use_smooth=True
    return dict(scenery='Original venue-inspired '+profile['kind'],version=plan['version'],
                trees=len(plan['trees']),structures=len(plan['structures']),lake=bool(plan['lake']),mesh_faces=len(faces))

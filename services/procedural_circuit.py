"""Construct a stylized 3D asphalt strip from a complete telemetry reference.

Not surveyed centre lines, circuit widths, elevation or scenery. Elevation, when
usable, is a smoothed relative telemetry estimate, never a surveyed height map.
The same
distance-based motion and asphalt footprint validation apply as licensed assets.
"""
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree, Delaunay
from scipy.interpolate import LinearNDInterpolator
from services.driving_path import arc_route,directions,RoadGuide


def strip_mesh(points,half_width=6.,heights=None):
    """Road and alternating kerb quads. Material zero is asphalt only."""
    points=np.asarray(points,dtype=float)
    heights=np.zeros(len(points)) if heights is None else np.asarray(heights,dtype=float)
    if heights.shape!=(len(points),) or not np.isfinite(heights).all():
        raise ValueError('Road heights must match the finite circuit points.')
    tangent=directions(points); side=np.column_stack([-tangent[:,1],tangent[:,0]])
    distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    vertices=[]
    for lateral in (-half_width-.9,-half_width,half_width,half_width+.9):
        ring=points+side*lateral
        vertices.extend(np.column_stack([ring,heights]).tolist())
    n=len(points); faces=[]; materials=[]
    for i in range(n-1):
        for band in range(3):
            faces.append([band*n+i,band*n+i+1,(band+1)*n+i+1,(band+1)*n+i])
            materials.append(0 if band==1 else (2 if int(distance[i]/4)%2 else 3))
    return {'vertices':vertices,'faces':faces,'materials':materials,'half_width_metres':half_width}


def telemetry_elevation(reference,points):
    """Conservative relative grade from metre-scaled telemetry, or explicit flat fallback.

    Reject drift, spikes and implausible grades rather than inventing hills. A
    metre-spaced periodic filter removes GPS quantisation without amplifying the
    source range. XY, clocks, distance progress and lap deltas are not changed.
    """
    reference=np.asarray(reference,dtype=float);points=np.asarray(points,dtype=float)
    xy=reference[:,1:3];z=reference[:,3]
    distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
    metadata=dict(source='Telemetry Z (smoothed relative metres)',surveyed=False,
                  status='flat-fallback',source_range_metres=float(np.ptp(z)))
    def flat(reason):
        return np.zeros(len(points)),dict(metadata,reason=reason,range_metres=0.,max_grade=0.)
    if not np.isfinite(z).all() or distance[-1]<100:
        return flat('No finite complete elevation trace.')
    if np.ptp(z)<.3:
        return flat('Elevation channel is constant or below reliable vertical resolution.')
    if np.ptp(z)>350:
        return flat('Elevation range is implausible for a circuit lap.')
    if abs(z[-1]-z[0])>max(2.,float(np.ptp(z))*.08):
        return flat('Elevation does not close at the start/finish line.')
    grade=np.abs(np.diff(z))/np.maximum(np.diff(distance),1.)
    if np.max(grade)>.45 or np.quantile(grade,.99)>.30:
        return flat('Elevation contains implausible vertical jumps or grades.')
    keep=np.r_[True,np.diff(distance)>1e-6]
    distance=distance[keep];xy=xy[keep];z=z[keep]
    count=max(128,int(np.ceil(distance[-1]/2.)))
    grid=np.linspace(0,distance[-1],count+1)
    regular=np.interp(grid,distance,z)
    regular[0]=regular[-1]=(regular[0]+regular[-1])/2
    smooth=gaussian_filter1d(regular[:-1],10./(distance[-1]/count),mode='wrap')
    smooth=np.r_[smooth,smooth[0]]
    # Project each road vertex onto its nearest original telemetry segment.
    # This retains the height/location correspondence after XY-only smoothing.
    a=xy[:-1];segments=np.diff(xy,axis=0)
    _,nearest=cKDTree((a+xy[1:])*.5).query(points,k=min(6,len(a)))
    if nearest.ndim==1:nearest=nearest[:,None]
    v=segments[nearest];base=a[nearest]
    fraction=np.clip(np.sum((points[:,None,:]-base)*v,axis=2)/
                     np.maximum(np.sum(v*v,axis=2),1e-9),0,1)
    errors=np.sum((points[:,None,:]-(base+v*fraction[:,:,None]))**2,axis=2)
    best=np.argmin(errors,axis=1);rows=np.arange(len(points));index=nearest[rows,best]
    along=distance[index]+fraction[rows,best]*(distance[index+1]-distance[index])
    heights=np.interp(along,grid,smooth)
    heights-=float(np.median(heights))
    heights[0]=heights[-1]=(heights[0]+heights[-1])/2
    ds=np.maximum(np.linalg.norm(np.diff(points,axis=0),axis=1),1e-6)
    max_grade=float(np.max(np.abs(np.diff(heights))/ds))
    if max_grade>.30:
        return flat('Elevation cannot be aligned smoothly with this telemetry layout.')
    return heights,dict(metadata,status='telemetry-estimated',reason='Not surveyed; no banking inferred.',
                        range_metres=float(np.ptp(heights)),max_grade=max_grade,
                        smoothing_metres=10.)


def terrain_mesh(road_mesh,margin=1200.,spacing=80.):
    """Original surrounding terrain attached to road heights, not surveyed geography.

    Close road anchors preserve depth precision; distant coarse tiles interpolate
    nearby road heights only. The terrain sits 18 cm below the asphalt/kerbs.
    """
    road=np.asarray(road_mesh['vertices'],dtype=float)
    n=len(road)//4
    indices=np.unique(np.r_[np.arange(0,n,4),n-1]).astype(int)
    anchors=road.reshape(4,n,3)[:,indices,:].reshape(-1,3)
    lo=np.floor((road[:,:2].min(axis=0)-margin)/spacing)*spacing
    hi=np.ceil((road[:,:2].max(axis=0)+margin)/spacing)*spacing
    gx,gy=np.meshgrid(np.arange(lo[0],hi[0]+spacing*.5,spacing),
                      np.arange(lo[1],hi[1]+spacing*.5,spacing))
    grid=np.column_stack([gx.ravel(),gy.ravel()])
    distance,index=cKDTree(anchors[:,:2]).query(grid,k=8)
    # Do not insert coarse-grid vertices within the accurately anchored road.
    outside=distance[:,0]>float(road_mesh['half_width_metres'])+12
    weights=1/np.maximum(distance,2.)**2
    height=np.sum(anchors[index,2]*weights,axis=1)/np.sum(weights,axis=1)
    vertices=np.vstack([anchors,np.column_stack([grid[outside],height[outside]])])
    _,keep=np.unique(vertices[:,:2],axis=0,return_index=True)
    vertices=vertices[np.sort(keep)]
    vertices[:,2]-=.18
    triangles=Delaunay(vertices[:,:2])
    return dict(vertices=vertices.tolist(),faces=triangles.simplices.tolist(),
                description='Illustrative terrain interpolated from telemetry road grade; not surveyed.')


def terrain_clearance(road_mesh,terrain):
    """Test road faces, not only shared anchors, before enabling an elevation mesh."""
    ground=np.asarray(terrain['vertices']);sample=LinearNDInterpolator(ground[:,:2],ground[:,2])
    road=np.asarray(road_mesh['vertices']).reshape(4,-1,3)
    probes=[(road[:,:-1]+road[:,1:])*.5,
            (road[:-1,:-1]+road[1:,:-1]+road[:-1,1:]+road[1:,1:])*.25]
    for corners in ((road[:-1,:-1],road[:-1,1:],road[1:,1:]),
                    (road[:-1,:-1],road[1:,1:],road[1:,:-1])):
        probes.append(sum(corners)/3)
    return min(float(np.nanmin(q[:,:,2]-sample(q[:,:,:2]))) for q in probes)


def build_circuit(comparison):
    reference=np.asarray(comparison.track,dtype=float)
    if reference.ndim!=2 or reference.shape[1]!=4 or len(reference)<128 or not np.isfinite(reference).all():
        raise ValueError('3D requires a complete finite telemetry layout. Use 2D for this lap.')
    original=reference[:,1:3].copy()
    if np.linalg.norm(original[0]-original[-1])>35:
        raise ValueError('Telemetry does not close this circuit safely. Choose a complete non-pit lap or use 2D.')
    original[0]=original[-1]=(original[0]+original[-1])/2
    _,points,length=arc_route(original,spacing=2.)
    if not 2000<=length<=9000:
        raise ValueError('Telemetry layout has an implausible circuit length. Choose another lap or use 2D.')
    ring=gaussian_filter1d(points[:-1],2.,axis=0,mode='wrap')
    _,points,_=arc_route(np.vstack([ring,ring[0]]))
    origin=points.mean(axis=0); points-=origin
    heights,elevation=telemetry_elevation(reference,points+origin)
    mesh=strip_mesh(points,heights=heights)
    mesh['elevation']=elevation
    if elevation['status']=='telemetry-estimated':
        terrain=terrain_mesh(mesh)
        clearance=terrain_clearance(mesh,terrain)
        if not np.isfinite(clearance) or clearance<.10:
            # Constant-width telemetry strips can overlap around tight parallel
            # roads/hairpins (notably Monaco). Without surveyed bridges/tunnels,
            # a heightfield cannot safely represent both layers. Do not export
            # ground through asphalt or silently invent that missing geometry.
            heights=np.zeros(len(points))
            elevation=dict(elevation,status='flat-fallback',range_metres=0.,max_grade=0.,
                reason='Vertically overlapping telemetry road strips need surveyed bridge/tunnel geometry; kept flat safely.')
            mesh=strip_mesh(points,heights=heights);mesh['elevation']=elevation
        else:
            terrain['minimum_road_clearance_metres']=clearance
            mesh['terrain']=terrain
    quads=np.array(mesh['faces'])[np.array(mesh['materials'])==0]
    triangles=np.vstack([quads[:,[0,1,2]],quads[:,[0,2,3]]])
    # Generated road is still validated, not assumed safe around hairpins.
    guide=RoadGuide(np.array(mesh['vertices']),triangles)
    route=guide.route(points)
    route['source_origin']=origin.tolist()
    route['elevation_profile']=dict(xy=points.tolist(),z=heights.tolist(),
        progress=np.linspace(0,1,len(points)).tolist(),metadata=elevation)
    return mesh,route

"""Smooth, distance-parameterized display routes constrained to licensed asphalt.

This changes ghost-lap geometry only. Lap clocks/progress/delta remain source data.
"""
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt, gaussian_filter1d, map_coordinates, minimum_filter1d
from scipy.spatial import cKDTree


def arc_route(xy, spacing=.8):
    """Resample a closed route by geometric distance, not noisy GPS sample time."""
    xy=np.asarray(xy,dtype=float)
    distance=np.r_[0.,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
    valid=np.r_[True,np.diff(distance)>1e-6]
    distance=distance[valid]; xy=xy[valid]
    if distance[-1]<100: raise ValueError('3D display route is too short.')
    progress=np.linspace(0,1,max(128,int(np.ceil(distance[-1]/spacing))+1))
    points=np.column_stack([np.interp(progress*distance[-1],distance,xy[:,i]) for i in range(2)])
    return progress,points,float(distance[-1])


def directions(points):
    ring=points[:-1]
    tangent=np.roll(ring,-1,axis=0)-np.roll(ring,1,axis=0)
    tangent/=np.linalg.norm(tangent,axis=1)[:,None]
    return np.vstack([tangent,tangent[0]])


class RoadGuide:
    def __init__(self,vertices,triangles,step=.4):
        polygons=np.asarray(vertices)[triangles][:,:,:2]
        self.origin=polygons.reshape(-1,2).min(axis=0)-2
        self.step=step
        size=np.ceil((polygons.reshape(-1,2).max(axis=0)-self.origin+2)/step).astype(int)
        mask=Image.new('1',tuple(size)); draw=ImageDraw.Draw(mask)
        for triangle in (polygons-self.origin)/step:
            draw.polygon([tuple(point) for point in triangle],fill=1)
        self.clearances=distance_transform_edt(np.asarray(mask,dtype=bool),sampling=step).astype(np.float32)
        row,col=np.nonzero(self.clearances>=2.8)
        self.safe_points=self.origin+np.column_stack([col,row])*step
        if not len(self.safe_points):
            raise ValueError('Available asphalt is too narrow for a safe 3D display route. Use 2D.')
        self.tree=cKDTree(self.safe_points)

    def clearance(self,points):
        points=np.asarray(points)
        pixel=(points.reshape(-1,2)-self.origin)/self.step
        result=map_coordinates(self.clearances,[pixel[:,1],pixel[:,0]],order=1,mode='constant',cval=0)
        return result.reshape(points.shape[:-1])

    def route(self,reference,max_separation=1.25,max_correction=12.):
        original=np.asarray(reference,dtype=float).copy()
        if np.linalg.norm(original[0]-original[-1])>35:
            raise ValueError('3D reference does not form a complete circuit.')
        original[0]=original[-1]=(original[0]+original[-1])/2
        _,points,length=arc_route(original,spacing=2.)
        ring=points[:-1]
        # Gentle periodic geometry filtering. Do NOT filter car time/positions.
        ring=gaussian_filter1d(ring,2.,axis=0,mode='wrap')
        if max_correction>12:
            distance,nearest=self.tree.query(ring)
            if distance.max()>max_correction:
                raise ValueError('Reference cannot be aligned safely to the source asphalt. The model was not changed.')
            outside=self.clearance(ring)<.6
            ring[outside]=self.safe_points[nearest[outside]]
            ring=gaussian_filter1d(ring,1.5,axis=0,mode='wrap')
        heading=np.roll(ring,-1,axis=0)-np.roll(ring,1,axis=0)
        heading/=np.linalg.norm(heading,axis=1)[:,None]
        lateral=np.column_stack([-heading[:,1],heading[:,0]])
        cross_offsets=np.arange(-12.,12.001,.2)
        cross_clearance=self.clearance(ring[:,None,:]+lateral[:,None,:]*cross_offsets[None,:,None])
        for index,row in enumerate(cross_clearance):
            valid=np.flatnonzero(row>=.6)
            if not len(valid): raise ValueError('No asphalt cross-section near the reference route.')
            nearest=valid[np.argmin(np.abs(cross_offsets[valid]))]
            left=nearest; right=nearest
            while left>0 and row[left-1]>=.6: left-=1
            while right+1<len(row) and row[right+1]>=.6: right+=1
            # Centre the same contiguous road strip, never jump to a wider
            # neighbouring layout or infer an individual driver's racing line.
            center=cross_offsets[(left+right)//2]
            ring[index]+=lateral[index]*center
        for _ in range(12):
            distance,nearest=self.tree.query(ring)
            if distance.max()>max_correction:
                raise ValueError('No safe asphalt route near this telemetry reference. Use 2D.')
            needs=self.clearance(ring)<2.65
            ring[needs]=self.safe_points[nearest[needs]]
            ring=gaussian_filter1d(ring,1.5,axis=0,mode='wrap')
        progress,points,length=arc_route(np.vstack([ring,ring[0]]))
        tangent=directions(points)
        side=np.column_stack([-tangent[:,1],tangent[:,0]])
        # Reject a route rather than exporting cars in runoff. Test the entire
        # body footprint, including front/rear corners, not just root centres.
        offsets=np.full(len(points),max_separation)
        for separation in np.arange(max_separation,-.001,-.05):
            safe=np.ones(len(points),dtype=bool)
            for sign in (-1,1):
                for along in (-2.3,0.,3.):
                    for lateral in (-1.15,0.,1.15):
                        corner=points+tangent*along+side*(sign*separation+lateral)
                        safe&=self.clearance(corner)>=.55
            failed=~safe & (offsets>=separation)
            offsets[failed]=max(0.,separation-.05)
        # Anticipate narrowing well ahead of a bend, then taper gently by road
        # distance. Never snap sideways from one frame to the next.
        ds=length/(len(points)-1)
        safe=offsets[:-1]
        envelope=minimum_filter1d(safe,size=max(3,int(50/ds)|1),mode='wrap')
        offsets=gaussian_filter1d(envelope,max(1.,8/ds),mode='wrap')
        offsets-=max(0.,float(np.max(offsets-safe)))
        offsets=np.maximum(0.,offsets)
        offsets=np.r_[offsets,offsets[0]]
        for sign in (-1,1):
            for along in (-2.3,0.,3.):
                for lateral in (-1.15,0.,1.15):
                    if self.clearance(points+tangent*along+side*(sign*offsets+lateral)[:,None]).min()<.5:
                        raise ValueError('Available circuit cannot contain both car footprints safely. Use 2D.')
        return {'progress':progress.tolist(),'xy':points.tolist(),'half_separation':offsets.tolist(),
                'separation_range':[float(offsets.min()*2),float(offsets.max()*2)],
                'length_metres':length,'minimum_center_clearance':float(self.clearance(points).min())}

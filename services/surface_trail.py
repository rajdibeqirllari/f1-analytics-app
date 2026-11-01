"""World-space paint ribbon sampled from the very same pose function as cars.

NumPy only: usable in Blender's Python. No screen-space/camera transforms and
no approximate shader time cut. Each frame has exact timed head/tail vertices.
"""
import numpy as np
from scripts.cinematic_math import motion_progress


class DistanceClock:
    def __init__(self,samples):
        self.samples=samples;self.t=np.asarray(samples['t'],float)
        self.v=np.asarray(samples['speed'],float)/3.6;self.dt=np.diff(self.t)
        if self.t.ndim!=1 or len(self.t)<2 or self.v.shape!=self.t.shape or not np.isfinite(self.t).all() or not np.isfinite(self.v).all() or np.any(self.v<0):
            raise ValueError('Trail needs finite, nonnegative speed samples.')
        self.s=np.r_[0.,np.cumsum((self.v[:-1]+self.v[1:])*.5*self.dt)]
        if np.any(self.dt<=0) or self.s[-1]<=0:raise ValueError('Trail needs ordered moving telemetry.')

    def progress(self,t):return motion_progress(self.samples,t)

    def time(self,p):
        distance=np.clip(np.asarray(p),0,1)*self.s[-1]
        i=np.clip(np.searchsorted(self.s,distance,side='right')-1,0,len(self.t)-2)
        ds=np.maximum(0,distance-self.s[i]);a=(self.v[i+1]-self.v[i])/self.dt[i]
        # Stable inverse of ds=v*dt+a*dt²/2, including constant speed and stops.
        denominator=self.v[i]+np.sqrt(np.maximum(0,self.v[i]**2+2*a*ds))
        delta=np.divide(2*ds,denominator,out=np.zeros_like(ds,dtype=float),where=denominator>1e-12)
        return self.t[i]+np.clip(delta,0,self.dt[i])


class SurfaceRibbon:
    def __init__(self,pose,project,raw_progress,length,half_width=.12,lift=.002,spacing=.20):
        self.pose=pose;self.project=project;self.width=half_width;self.lift=lift
        self.raw_progress=np.asarray(raw_progress,float)
        p=np.unique(np.r_[self.raw_progress,np.linspace(0,1,int(np.ceil(length/spacing))+1)])
        # Adaptive curvature sampling preserves the actual car spline rather
        # than applying a different smoothing filter to a decorative polyline.
        for _ in range(8):
            centers=np.array([pose(v)[0] for v in p]);mid=(p[1:]+p[:-1])*.5
            actual=np.array([pose(v)[0] for v in mid])
            error=np.linalg.norm((actual-(centers[1:]+centers[:-1])*.5)[:,:2],axis=1)
            bad=(error>.0005)|(np.linalg.norm(np.diff(centers[:,:2],axis=0),axis=1)>.25)
            if not bad.any():break
            p=np.unique(np.r_[p,mid[bad]])
        else:raise ValueError('Could not resolve the trajectory ribbon to sub-millimetre chord accuracy.')
        self.p=p;self.centers=centers;self.rows=np.array([self.row(v) for v in p])
        self.metrics=dict(points=len(p),max_spacing_metres=float(np.linalg.norm(np.diff(centers[:,:2],axis=0),axis=1).max()),
            max_curve_chord_error_metres=float(error.max()),paint_lift_metres=lift,
            off_asphalt_vertices=0,max_face_surface_clearance_metres=0.,min_face_surface_clearance_metres=1.)
        # A planar quad can bridge a triangulated road seam. Validate its actual
        # triangle centroids against the authoritative asphalt BVH, not terrain.
        for a,b in zip(self.rows[:-1],self.rows[1:]):
            for q in ((a[0]+b[0]+b[1])/3,(a[0]+b[1]+a[1])/3):
                ground=project(q[:2]);clearance=float(q[2]-ground[2])
                self.metrics['max_face_surface_clearance_metres']=max(self.metrics['max_face_surface_clearance_metres'],clearance)
                self.metrics['min_face_surface_clearance_metres']=min(self.metrics['min_face_surface_clearance_metres'],clearance)
                if not -.0005<=clearance<=.006:
                    raise ValueError('Trail face does not conform closely enough to the asphalt.')

    def row(self,p):
        center,tangent=self.pose(float(p));normal=np.array([-tangent[1],tangent[0]],float)
        normal/=max(1e-12,np.linalg.norm(normal))
        rows=[]
        for sign in (-1,1):
            q=np.asarray(self.project(center[:2]+sign*self.width*normal),float).copy()
            q[2]+=self.lift;rows.append(q)
        return np.array(rows)

    def frame(self,clock,elapsed,trail_time,lifetime=.28,layer=.0):
        start=max(float(clock.t[0]),float(trail_time)-lifetime)
        end=min(float(elapsed),float(clock.t[-1]))
        if end<=start:return np.empty((0,3)),np.empty(0),np.empty(0)
        first,last=map(float,clock.progress(np.array([start,end])))
        if last-first<1e-12:return np.empty((0,3)),np.empty(0),np.empty(0)
        lo=np.searchsorted(self.p,first,side='right');hi=np.searchsorted(self.p,last,side='left')
        p=np.r_[first,self.p[lo:hi],last]
        rows=np.concatenate([self.row(first)[None],self.rows[lo:hi],self.row(last)[None]],axis=0).copy()
        rows[:,:,2]+=layer
        times=np.r_[start,clock.time(p[1:-1]),end]
        alpha=np.clip(1-(trail_time-times)/lifetime,0,1)**2
        return rows.reshape(-1,3),np.repeat(times,2),np.repeat(alpha,2)

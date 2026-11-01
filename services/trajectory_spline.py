"""Shape-preserving C1 route interpolation, with bounded corridor deviation."""
import numpy as np


class RouteSpline:
    def __init__(self,progress,points,max_deviation=.12):
        self.p=np.asarray(progress,float);self.xyz=np.asarray(points,float)
        h=np.diff(self.p)
        if len(h)<1 or np.any(h<=0):raise ValueError('Route progress must be strictly increasing.')
        delta=np.diff(self.xyz,axis=0)/h[:,None];self.slopes=np.zeros_like(self.xyz)
        if len(h)==1:self.slopes[:]=delta[0]
        else:
            # Fritsch–Carlson weighted harmonic slopes: C1 and no component
            # extrema beyond source anchors. Implemented in NumPy for Blender.
            left,right=delta[:-1],delta[1:];same=left*right>0
            w1=(2*h[1:]+h[:-1])[:,None];w2=(h[1:]+2*h[:-1])[:,None]
            denominator=w1/np.where(same,left,1)+w2/np.where(same,right,1)
            self.slopes[1:-1]=np.where(same,(w1+w2)/np.where(same,denominator,1),0)
            for index,h0,h1,d0,d1 in ((0,h[0],h[1],delta[0],delta[1]),(-1,h[-1],h[-2],delta[-1],delta[-2])):
                slope=((2*h0+h1)*d0-h0*d1)/(h0+h1)
                slope=np.where(np.sign(slope)!=np.sign(d0),0,slope)
                self.slopes[index]=np.where((np.sign(d0)!=np.sign(d1))&(np.abs(slope)>3*np.abs(d0)),3*d0,slope)
        self.max_deviation=max_deviation

    def point(self,p):
        p=np.clip(p,self.p[0],self.p[-1]);i=np.clip(np.searchsorted(self.p,p,side='right')-1,0,len(self.p)-2)
        h=self.p[i+1]-self.p[i];t=(p-self.p[i])/h
        point=(2*t**3-3*t*t+1)*self.xyz[i]+(t**3-2*t*t+t)*h*self.slopes[i]
        point+=(-2*t**3+3*t*t)*self.xyz[i+1]+(t**3-t*t)*h*self.slopes[i+1]
        linear=np.array([np.interp(p,self.p,self.xyz[:,i]) for i in range(3)])
        delta=point-linear;length=np.linalg.norm(delta)
        if length>self.max_deviation:point=linear+delta*self.max_deviation/length
        return point

    def pose(self,p):
        point=self.point(p);step=1e-5
        tangent=self.point(min(self.p[-1],p+step))-self.point(max(self.p[0],p-step))
        tangent/=max(1e-9,np.linalg.norm(tangent))
        return point,tangent

"""Fixed-aspect 3D locator: the same timed route and ghost offsets as Blender."""
import numpy as np
from PIL import Image, ImageDraw, ImageColor
from scripts.cinematic_math import motion_progress, ghost_lane_side


class TrackMap:
    def __init__(self, comparison, driving_path, box, scale, font, colors=None):
        self.comparison=comparison; self.box=tuple(round(v*scale) for v in box)
        self.colors=colors or ('#ff4555','#37d9ee')
        self.scale=scale; self.font=font
        track=comparison.track
        self.progress=np.asarray(driving_path['progress'] if driving_path else track[:,0])
        self.route=np.asarray(driving_path['xy'] if driving_path else track[:,1:3])
        self.separation=np.asarray(driving_path['half_separation'] if driving_path else np.zeros(len(track)))
        x,y,w,h=self.box
        self.low=self.route.min(axis=0); span=np.maximum(self.route.max(axis=0)-self.low,1)
        self.factor=min((w-28*scale)/span[0],(h-47*scale)/span[1])
        self.origin=np.array([x+(w-span[0]*self.factor)/2,y+23*scale+(h-43*scale-span[1]*self.factor)/2])
        self.static=Image.new('RGBA', (x+w+2,y+h+2))
        d=ImageDraw.Draw(self.static)
        d.rounded_rectangle((x,y,x+w,y+h),radius=round(9*scale),fill=(9,20,31,238),outline=(53,79,94,210))
        d.text((x+11*scale,y+6*scale),'TRACK POSITION',font=font(max(8,round(9*scale)),True),fill='#91adb9')
        points=[tuple(p) for p in self.project(self.route)]
        d.line(points,fill=(31,53,69,255),width=max(3,round(6*scale)),joint='curve')
        d.line(points,fill='#829eac',width=max(1,round(1.5*scale)),joint='curve')
        start=points[0]; r=2*scale
        d.rectangle((start[0]-r,start[1]-r,start[0]+r,start[1]+r),fill='#f5f7fa')
        for index,lap in enumerate(comparison.laps):
            color=self.colors[index]; lx=x+11*scale+index*w/2
            d.ellipse((lx,y+h-13*scale,lx+4*scale,y+h-9*scale),fill=color)
            d.text((lx+8*scale,y+h-17*scale),lap.code,font=font(max(8,round(9*scale)),True),fill=color)

    def project(self, xy):
        point=(np.asarray(xy)-self.low)*self.factor
        point[...,1]=(self.route[:,1].max()-self.low[1])*self.factor-point[...,1]
        return point+self.origin

    def position(self,index,elapsed):
        return self.positions(index,np.asarray([elapsed]))[0]

    def positions(self,index,elapsed):
        """Evaluate the whole locator trail together, integrating lap speed once."""
        p=motion_progress(self.comparison.laps[index].samples,elapsed)
        point=np.stack([np.interp(p,self.progress,self.route[:,axis]) for axis in (0,1)],axis=-1)
        step=2/(len(self.route)-1)
        tangent=np.stack([np.interp(np.minimum(1,p+step),self.progress,self.route[:,axis])-
                          np.interp(np.maximum(0,p-step),self.progress,self.route[:,axis]) for axis in (0,1)],axis=-1)
        tangent/=np.maximum(np.linalg.norm(tangent,axis=-1),1e-9)[...,None]
        point+=np.stack([-tangent[...,1],tangent[...,0]],axis=-1)*(np.interp(p,self.progress,self.separation)*ghost_lane_side(index))[...,None]
        return point

    def draw(self,layer,elapsed):
        layer.alpha_composite(self.static)
        d=ImageDraw.Draw(layer); s=self.scale
        for index,color in enumerate(self.colors):
            # Recent movement is a restrained colored ribbon; locations are never offset for UI.
            tail=self.project(self.positions(index,np.linspace(max(0,elapsed-3),elapsed,18)))
            d.line([tuple(p) for p in tail],fill=color,width=max(1,round(2*s)),joint='curve')
            x,y=tail[-1]
            r=(4.5 if index==0 else 3)*s
            d.ellipse((x-r-3*s,y-r-3*s,x+r+3*s,y+r+3*s),fill=(*ImageColor.getrgb(color),45))
            d.ellipse((x-r,y-r,x+r,y+r),fill=color,outline='#ffffff',width=max(1,round(s)))

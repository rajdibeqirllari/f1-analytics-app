import json,unittest
from pathlib import Path
import numpy as np
from services.cinematic_camera import cinematic_ghost_rig
from scripts.cinematic_math import project_cars


class CinematicBoundsTests(unittest.TestCase):
    def test_actual_pitched_model_bounds_fit_hud_without_changing_car_poses(self):
        metadata=json.loads((Path(__file__).resolve().parents[1]/'assets/3d/cars/qvist/metadata.json').read_text())[0]
        objects=[o for o in metadata['objects'] if o['type']=='MESH']
        low=np.min([o['min'] for o in objects],axis=0);high=np.max([o['max'] for o in objects],axis=0)
        corners=np.array([[x,y,z] for x in (low[0],high[0]) for y in (low[1],high[1]) for z in (low[2],high[2])])
        t=np.arange(240)/60;yaw=t*1.8;grade=.34*np.sin(t*5)
        heading=np.column_stack([np.cos(yaw)*np.cos(grade),np.sin(yaw)*np.cos(grade),np.sin(grade)])
        center=np.cumsum(heading*.9,axis=0)
        positions=np.stack([center,center-heading*(3+4*np.sin(t*2)**2)[:,None]],axis=1)
        tangents=np.stack([heading,heading],axis=1);original=positions.copy()
        for size in ((540,960),(960,540)):
            for overhead in (False,True):
                loc,target,_,_=cinematic_ghost_rig(positions,tangents,60,size,overhead=overhead,local_corners=corners)
                q=project_cars(positions,tangents,loc,target,size,local_corners=corners)
                if size[0]>size[1]:q[:,:,:,0]-=.1
                q[:,:,:,1]+=.1*max(1,size[0]/size[1])
                self.assertGreater(q[:,:,:,0].min(),.08);self.assertLess(q[:,:,:,0].max(),.90)
                self.assertGreater(q[:,:,:,1].min(),.38 if size[1]>size[0] else .40)
                self.assertLess(q[:,:,:,1].max(),.80)
                self.assertGreater(q[:,:,:,2].min(),0)
        np.testing.assert_array_equal(positions,original)

    def test_projection_applies_road_pitch_to_model_corners(self):
        p=np.zeros((1,2,3));h=np.broadcast_to([1.,0.,1.],p.shape).copy()
        corners=np.array([[0,-3,0],[0,3,0]])
        q=project_cars(p,h,np.array([[-15.,-8.,15.]]),np.zeros((1,3)),(540,960),local_corners=corners)
        flat=project_cars(p,np.broadcast_to([1.,0.,0.],p.shape).copy(),np.array([[-15.,-8.,15.]]),np.zeros((1,3)),(540,960),local_corners=corners)
        self.assertGreater(np.abs(q-flat).max(),.1)


if __name__=='__main__':unittest.main()

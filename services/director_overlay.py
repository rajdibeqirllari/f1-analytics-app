"""RACE HYPE social-director graphics. Gaps always compare matched distance."""
import math
import numpy as np
from PIL import Image, ImageDraw
from services.video_branding import LOGO, _sprite
from services.video_minimap import TrackMap

WHITE='#f4f7fb';MUTED='#a4b7c7';RED='#ff4c50';GREEN='#42e0b8'


def lap_clock(seconds):
    minutes,remainder=divmod(max(0,round(float(seconds)*1000)),60000)
    return f'{minutes}:{remainder/1000:06.3f}'


def _seconds(value):
    try:
        result=float(value.total_seconds() if hasattr(value,'total_seconds') else value)
        return result if math.isfinite(result) and result>0 else None
    except (TypeError,ValueError):return None


class DirectorTelemetryOverlay:
    def __init__(self,comparison,size,start,end,full,driving_path,colors,font):
        self.comparison=comparison;self.size=size;self.start=start;self.end=end;self.full=full
        self.portrait=size[1]>size[0];self.scale=size[0]/(540 if self.portrait else 960)
        self.colors=colors;self.font=font;self.path=driving_path or {}
        self.progress=np.linspace(0,1,401)
        self.deltas=np.array([comparison.delta_at(p) for p in self.progress])
        self.delta_limit=max(.05,float(np.max(np.abs(self.deltas)))*1.18)
        # Never invent sector timing by dividing the circuit into equal thirds.
        sectors=[_seconds(v) for v in comparison.laps[0].sectors];self.sectors=[]
        if len(sectors)==3 and all(v is not None for v in sectors) and abs(sum(sectors)-comparison.laps[0].lap_time)<.25:
            self.sectors=[float(comparison.laps[0].progress_at(t)) for t in np.cumsum(sectors)[:-1]]
        self.chart_box=(26,600,450,96) if self.portrait else (250,358,460,76)
        self.map_box=(26,708,114,96) if self.portrait else (28,362,200,130)
        self.rows=[(150,708,326,46),(150,758,326,46)] if self.portrait else [(250,444,330,46),(590,444,330,46)]
        self.map=TrackMap(comparison,driving_path,self.map_box,self.scale,font,colors)
        self.brand_position=(26,818) if self.portrait else (790,26)
        self.brand=_sprite(round((100 if self.portrait else 130)*self.scale),round((74 if self.portrait else 86)*self.scale),LOGO.stat().st_mtime_ns)
        self.background=Image.new('RGBA',size);d=ImageDraw.Draw(self.background);w,h=size
        top=round((215 if self.portrait else 130)*self.scale)
        for y in range(min(h,top)):d.line((0,y,w,y),fill=(4,9,15,round(150*(1-y/top))))
        bottom=round((584 if self.portrait else 345)*self.scale)
        for y in range(bottom,h):d.line((0,y,w,y),fill=(4,9,15,round(155*(y-bottom)/max(1,h-bottom))))

    def state(self,elapsed):
        states=[lap.at(elapsed) for lap in self.comparison.laps]
        p=min(v['progress'] for v in states);delta=self.comparison.delta_at(p)
        return dict(laps=states,progress=p,delta=delta,leader=None if abs(delta)<.0005 else 0 if delta>0 else 1,
                    finished=self.full and elapsed>=self.comparison.duration)

    def render(self,source,elapsed,output_time=None):
        s=self.scale;layer=self.background.copy();d=ImageDraw.Draw(layer);c=self.comparison;live=self.state(elapsed)
        def xy(x,y):return round(x*s),round(y*s)
        def text(x,y,value,size=11,color=WHITE,bold=False,anchor=None):
            d.text(xy(x,y),str(value),font=self.font(max(8,round(size*s)),bold),fill=color,anchor=anchor)
        def line(x1,y1,x2,y2,color,width=1):
            d.line((*xy(x1,y1),*xy(x2,y2)),fill=color,width=max(1,round(width*s)))
        def panel(x,y,w,h,radius=10):
            d.rounded_rectangle((*xy(x,y),*xy(x+w,y+h)),radius=round(radius*s),fill=(8,16,25,232),outline=(72,95,114,125),width=max(1,round(s)))
        hx,hy=(26,100) if self.portrait else (28,28);right=476 if self.portrait else 710
        line(hx,hy+6,hx+14,hy+6,RED,3);text(hx+22,hy,'RACE HYPE  /  LAP DUEL',10,WHITE,True)
        speed=self.path.get('playback_speed',1)
        if speed!=1:text(right,hy,f'{speed:g}× SPEED',10,GREEN,True,'ra')
        event=c.event.replace(' Grand Prix','').upper();label=f'{event}  {c.year}  ·  {c.session.upper()}'
        if len(label)>58:label=label[:55]+'…'
        y=124 if self.portrait else 52;panel(hx,y,right-hx,80)
        line(hx+1,y+13,hx+1,y+67,RED,3);text(hx+14,y+8,label,8,MUTED,True)
        text(hx+14,y+24,lap_clock(min(elapsed,c.duration)),34,WHITE,True)
        leader=live['leader'];color=WHITE if leader is None else self.colors[leader]
        status='DEAD HEAT' if leader is None else c.laps[leader].code+(' WINS' if live['finished'] else ' AHEAD')
        text(right-152,y+31,status,12,color,True);text(right-14,y+46,f'{abs(live["delta"]):.3f}s',19,color,True,'ra')
        text(hx+15,y+65,'FINAL LAP GAP' if live['finished'] else 'TIME ADVANTAGE AT MATCHED DISTANCE',7,MUTED)
        x,cy,w,h=self.chart_box;panel(x,cy,w,h)
        text(x+12,cy+8,'THE ADVANTAGE',9,WHITE,True);text(x+w-12,cy+8,'SAME DISTANCE / SECONDS',7,MUTED,anchor='ra')
        gx,gy,gw,gh=x+12,cy+29,w-24,h-43;mid=gy+gh/2
        line(gx,mid,gx+gw,mid,'#465766');text(gx+2,gy-1,c.laps[0].code,7,self.colors[0]);text(gx+2,gy+gh-8,c.laps[1].code,7,self.colors[1])
        if self.sectors:
            bounds=[0,*self.sectors,1]
            for i in range(3):text(gx+gw*(bounds[i]+bounds[i+1])/2,cy+h-11,f'S{i+1}',7,MUTED,anchor='ma')
            for p in self.sectors:line(gx+gw*p,gy,gx+gw*p,gy+gh,'#344452')
        else:
            for p in (0,.5,1):text(gx+gw*p,cy+h-11,f'{p:.0%}',7,MUTED,anchor='ma')
        count=max(1,int(np.searchsorted(self.progress,live['progress'],side='right')))
        pp=np.append(self.progress[:count],live['progress']);dd=np.append(self.deltas[:count],live['delta'])
        points=[(gx+p*gw,mid-v/self.delta_limit*gh/2) for p,v in zip(pp,dd)]
        for i in range(1,len(points)):line(*points[i-1],*points[i],self.colors[0 if dd[i]>=0 else 1],2)
        px,py=points[-1];line(px,gy,px,gy+gh,'#99adbb');px,py=xy(px,py);r=3*s
        d.ellipse((px-r,py-r,px+r,py+r),fill=WHITE)
        self.map.draw(layer,elapsed)
        for i,(lap,state,row) in enumerate(zip(c.laps,live['laps'],self.rows)):
            rx,ry,rw,rh=row;panel(rx,ry,rw,rh,7);line(rx+1,ry+8,rx+1,ry+rh-8,self.colors[i],3)
            text(rx+10,ry+4,lap.code,18,self.colors[i],True);text(rx+10,ry+27,lap.team[:18],8,MUTED)
            available=lambda channel:channel not in lap.unavailable_channels and not any(f'{channel} is unavailable' in w for w in lap.warnings)
            active=not state['finished'];speed=round(state['speed']) if active and math.isfinite(state['speed']) else '—'
            text(rx+142,ry+4,speed,20,WHITE,True,'ra');text(rx+142,ry+29,'KM/H',7,MUTED,anchor='ra')
            gear=state['gear'] if active and available('nGear') and available('gear') else '—'
            text(rx+177,ry+5,gear,18,WHITE,True,'ra');text(rx+177,ry+29,'GEAR',7,MUTED,anchor='ra')
            throttle_ok=active and available('Throttle') and available('throttle') and math.isfinite(state['throttle'])
            brake_ok=active and available('Brake') and available('brake');throttle=max(0,min(100,state['throttle'])) if throttle_ok else 0
            pedal_x,pedal_w=rx+193,rw-205;text(pedal_x,ry+6,f'T {round(throttle)}%' if throttle_ok else 'T —',8,GREEN if throttle_ok else MUTED,True)
            line(pedal_x,ry+20,pedal_x+pedal_w,ry+20,'#344653',3)
            if throttle>0:line(pedal_x,ry+20,pedal_x+pedal_w*throttle/100,ry+20,GREEN,3)
            braking=brake_ok and state['brake'];text(pedal_x,ry+26,'BRAKE ON' if braking else 'BRAKE OFF' if brake_ok else 'BRAKE —',7,RED if braking else MUTED,braking)
        layer.alpha_composite(self.brand,xy(*self.brand_position))
        if self.portrait:
            text(150,827,'CHASE THE DETAIL.',13,WHITE,True);text(150,850,'@theracehype',11,MUTED);text(150,870,'Who gains at the next corner?',8,MUTED)
        fy=906 if self.portrait else 506;fx=26 if self.portrait else 28
        fraction=min(1,max(0,(elapsed-self.start)/max(1e-9,self.end-self.start)))
        line(fx,fy-8,right,fy-8,'#344653');line(fx,fy-8,fx+(right-fx)*fraction,fy-8,RED)
        text(fx,fy,'Telemetry-driven 3D recreation · estimated racing line',7,MUTED)
        text(fx,fy+13,'Concept car: Qvist_designs · CC BY 4.0 · modified',7,MUTED)
        return Image.alpha_composite(source.convert('RGBA'),layer).convert('RGB')

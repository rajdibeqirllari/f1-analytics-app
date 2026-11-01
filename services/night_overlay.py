"""Compact telemetry and locator for the close night chase presentation."""
from PIL import Image,ImageDraw
from services.video_minimap import TrackMap
from services.video_branding import add_social_brand


class NightTelemetryOverlay:
    def __init__(self,comparison,size,start,end,full,driving_path,colors,font):
        self.comparison=comparison;self.size=size;self.start=start;self.end=end;self.full=full
        self.portrait=size[1]>size[0];self.scale=size[0]/(540 if self.portrait else 960)
        self.colors=colors;self.font=font
        self.environment_credit=driving_path.get('environment_credit')
        self.original_glb=driving_path.get('unmodified_glb',False)
        self.onboard=driving_path.get('onboard_ghost',False)
        # Portrait social-safe composition: leave top navigation, right actions
        # and bottom captions clear. Landscape keeps its existing placement.
        self.map=TrackMap(comparison,driving_path,(320,120,150,170) if self.portrait else (764,28,170,160),self.scale,font,colors)
        # These gradients never depend on lap time. Cache their exact pixels.
        width,height=self.size;s=self.scale
        self.background=Image.new('RGBA',self.size);d=ImageDraw.Draw(self.background)
        top=155 if self.portrait else 70
        for y in range(round(top*s)):
            d.line((0,y,width,y),fill=(4,9,16,round(210*(1-y/(top*s)))))
        bottom_px=round((760 if self.portrait else 405)*s)
        for y in range(bottom_px,height):
            alpha=round(232*((y-bottom_px)/max(1,height-bottom_px))**.65)
            d.line((0,y,width,y),fill=(3,7,12,alpha))

    def render(self,source,elapsed):
        width,height=self.size;s=self.scale;c=self.comparison
        layer=self.background.copy();d=ImageDraw.Draw(layer)
        def xy(x,y):return round(x*s),round(y*s)
        def text(x,y,value,size=11,color='#edf3fa',bold=False,anchor=None):
            d.text(xy(x,y),str(value),font=self.font(max(8,round(size*s)),bold),fill=color,anchor=anchor)
        def rect(x,y,w,h,color):d.rectangle((*xy(x,y),*xy(x+w,y+h)),fill=color)
        header_offset=85 if self.portrait else 0
        text(20,14+header_offset,'RACE HYPE  /  ONBOARD GHOST' if self.onboard else 'RACE HYPE  /  CHASE',10,'#a9bfce',True)
        event=c.event.replace(' Grand Prix','').upper()
        text(20,31+header_offset,event+'  '+str(c.year),18,bold=True)
        text(20,55+header_offset,c.session.upper()+'  /  SYNCHRONIZED GHOST LAPS',8,'#9aafbe')
        states=[lap.at(elapsed) for lap in c.laps]
        delta=c.delta_at(min(state['progress'] for state in states))
        for i,(lap,state,color) in enumerate(zip(c.laps,states,self.colors)):
            x=20;y=(167+i*158) if self.portrait else (92+i*150);w=132;h=140
            d.rounded_rectangle((*xy(x,y),*xy(x+w,y+h)),radius=round(7*s),fill=(7,15,24,230),outline=(73,94,112,190))
            rect(x,y,3,h,color)
            text(x+12,y+9,lap.code,24,color,True)
            text(x+w-10,y+17,'L'+str(lap.number),9,'#a9bfce',anchor='ra')
            text(x+12,y+35,lap.name.split()[-1],9,'#a9bfce')
            ms=round(state['elapsed']*1000);minutes,rem=divmod(ms,60000)
            text(x+12,y+49,f'{minutes}:{rem/1000:06.3f}',18,bold=True)
            signed=delta if i==1 else -delta
            text(x+12,y+75,'LEADER' if signed<=0 else f'+{signed:.3f}s',11,'#42ddc8' if signed<=0 else color,True)
            speed='—' if state['finished'] else round(state['speed'])
            text(x+12,y+92,speed,19,bold=True);text(x+52,y+102,'KM/H',7,'#9aafbe')
            gear='—' if state['finished'] or any('nGear is unavailable' in w for w in lap.warnings) else state['gear']
            text(x+w-10,y+96,'G'+str(gear),12,color,True,anchor='ra')
            throttle_ok=not state['finished'] and not any('Throttle is unavailable' in w for w in lap.warnings)
            brake_ok=not state['finished'] and not any('Brake is unavailable' in w for w in lap.warnings)
            text(x+12,y+117,'Throttle',7,'#a9bfce');text(x+w-10,y+117,'Brake',7,'#a9bfce',anchor='ra')
            rect(x+12,y+132,68,3,'#31404e');rect(x+90,y+132,30,3,'#31404e')
            if throttle_ok and state['throttle']>0:rect(x+12,y+132,68*min(100,max(0,state['throttle']))/100,3,'#22e66f')
            if brake_ok and state['brake']:rect(x+90,y+132,30,3,'#ff4555')
        self.map.draw(layer,elapsed)
        footer_y=931 if self.portrait else 498
        environment_line=('Track: Dave (@Tyler_Dave) · listed CC BY 4.0 · original GLB' if self.original_glb else
                          'Environment: Dave (@Tyler_Dave) · listed CC BY 4.0 · adapted')
        if self.environment_credit and self.portrait:
            text(20,916,environment_line,8,'#9aafbe')
        if not self.portrait:
            text(20,footer_y,environment_line if self.environment_credit else ('Estimated shared racing line · not measured trajectories' if self.onboard else 'Ghost display route · illustrative night scenery'),8,'#9aafbe')
        # User-requested bottom-edge footer, separate from the below-card logo.
        text(20,footer_y if self.portrait else footer_y+15,'Concept car: Qvist_designs · CC BY 4.0 · modified',8,'#9aafbe')
        y=902 if self.portrait else 484
        rect(20,y,(500 if self.portrait else 920),1,'#31404e')
        fraction=max(0,min(1,(elapsed-self.start)/(self.end-self.start)))
        rect(20,y,(500 if self.portrait else 920)*fraction,1,'#ff4555')
        return add_social_brand(Image.alpha_composite(source.convert('RGBA'),layer).convert('RGB'),placement='onboard_left' if self.onboard and not self.portrait else 'social_safe' if self.portrait else 'footer')

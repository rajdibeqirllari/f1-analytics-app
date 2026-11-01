"""THE LIMIT: animated 3D time sculpture, replay beats and signature payoff."""
import numpy as np
from PIL import Image, ImageDraw, ImageColor
from services.cinematic_overlay import CinematicTelemetryOverlay
from services.limit_story import LimitStory, INTRO_SECONDS


def ease(value):
    value = max(0., min(1., value))
    return value*value*(3-2*value)


class LimitTelemetryOverlay(CinematicTelemetryOverlay):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.story = LimitStory(self.comparison, self.path)

    def sculpture(self, time, outro=False):
        # Work in a fixed design space; final raster uses export resolution.
        w, h = (540, 960) if self.portrait else (960, 540)
        s = self.scale
        image = Image.new('RGBA', self.size, '#060b13')
        d = ImageDraw.Draw(image)
        def xy(x, y): return round(x*s), round(y*s)
        def text(x, y, value, size, color='#f4f7fb', anchor=None):
            d.text(xy(x,y), value, font=self.font(max(8,round(size*s)),True), fill=color, anchor=anchor)
        # Dark studio grid: explicitly an analytical space, not track scenery.
        cy = 445 if self.portrait else 225
        radius = 405 if self.portrait else 335
        for y in range(cy-100, cy+260, 24):
            d.line((*xy(18,y),*xy(w-18,y)),fill='#101f2c',width=max(1,round(s)))
        for x in range(-w,w*2,60):
            d.line((*xy(w/2+(x-w/2)*.22,cy-100),*xy(x,cy+260)),fill='#101f2c',width=max(1,round(s)))
        dive = 0 if outro else ease((time-2.65)/.55)
        focus = self.story.strongest['progress'] if self.story.strongest else .5
        base, ridge = self.story.project(-.55+.11*min(time,3.2), ease(time/.85) if not outro else 1,
                                         zoom=1+2.4*dive, focus=focus if dive else None)
        # Ease the focus origin too: no discontinuous jump at dive onset.
        if dive:
            b0,r0=self.story.project(-.55+.11*min(time,3.2),ease(time/.85),zoom=1+2.4*dive)
            base=b0*(1-dive)+base*dive;ridge=r0*(1-dive)+ridge*dive
        center=np.array([w/2 if self.portrait else 690,cy]);base=base*radius+center;ridge=ridge*radius+center
        def pts(points):return [xy(*v) for v in points]
        d.line(pts(base),fill='#334a5d',width=max(2,round(5*s)),joint='curve')
        # Painter's order keeps the extruded data curtain legible at crossings.
        order=np.argsort((base[:-1,1]+base[1:,1])*.5)
        for i in order:
            color=ImageColor.getrgb(self.colors[0 if self.story.delta[i]>=0 else 1])
            strength=.2+.8*min(1,abs(self.story.delta[i])/self.story.limit)
            shade=tuple(round(v*strength*.65) for v in color)
            d.polygon(pts([base[i],base[i+1],ridge[i+1],ridge[i]]),fill=shade)
        for i in range(0,600,8):
            d.line(pts([base[i],ridge[i]]),fill='#375568',width=max(1,round(s)))
        for i in range(600):
            d.line(pts(ridge[i:i+2]),fill=self.colors[0 if self.story.delta[i]>=0 else 1],width=max(2,round(3*s)))
        # White travelling spark makes the time sculpture readable as a lap.
        index=int(ease(min(time/2.5,1))*600)
        px,py=pts(ridge[index:index+1])[0];r=4*s
        d.ellipse((px-r,py-r,px+r,py+r),fill='#ffffff')
        x,y=(28,78) if self.portrait else (34,28)
        text(x,y,'RACE HYPE  /  THE LIMIT',12,'#42e0b8')
        event=self.comparison.event.replace(' Grand Prix','').upper()
        text(x,y+25,f'{event} · {self.comparison.year} · {self.comparison.session.upper()}',10,'#a4b7c7')
        title='THIS IS WHAT' if not outro else 'THE WHOLE LAP.'
        text(x,y+62,title,32 if self.portrait else 25)
        text(x,y+101,f'{self.gap:.3f} SECONDS',38 if self.portrait else 31,'#ffffff')
        text(x,y+148,'LOOKS LIKE.' if not outro else 'ONE TINY DIFFERENCE.',23 if self.portrait else 19,'#42e0b8')
        bottom=705 if self.portrait else 338
        text(28,bottom,'TIME CANYON  /  HEIGHT = TIME ADVANTAGE',10,'#ffffff')
        text(28,bottom+22,'Exaggerated timing sculpture · NOT track elevation',9,'#a4b7c7')
        for i,lap in enumerate(self.comparison.laps):
            text(28+i*160,bottom+48,lap.code+' ADVANTAGE',11,self.colors[i])
        if self.story.strongest:
            beat=self.story.strongest;code=self.comparison.laps[beat['driver']].code
            text(28,bottom+80,(f'{code} gains {beat["gain"]:.3f}s in the biggest 6% swing'),12)
        image.alpha_composite(self.brand,xy(28,h-105))
        text(130,h-100,'FOLLOW US ON',9,'#a4b7c7')
        text(130,h-80,'@theracehype',16)
        text(130,h-55,'YOUTUBE · INSTAGRAM · TIKTOK',8,'#a4b7c7')
        return image

    def render(self, source, elapsed, output_time=None):
        if output_time is None:
            output_time=max(0,(elapsed-self.start)/self.path.get('playback_speed',1))
        intro=self.path.get('timeline',{}).get('limit_intro_seconds',INTRO_SECONDS)
        action_time=max(0,output_time-intro)
        replay=super().render(source,elapsed,action_time).convert('RGBA')
        return self.from_replay(replay,elapsed,output_time)

    def from_replay(self, replay, elapsed, output_time):
        """Also supports a verified existing cinematic MP4 without double HUDs."""
        replay=replay.convert('RGBA')
        intro=self.path.get('timeline',{}).get('limit_intro_seconds',INTRO_SECONDS)
        action_time=max(0,output_time-intro)
        if output_time<intro:
            sculpture=self.sculpture(output_time)
            reveal=ease((output_time-(intro-.45))/.45)
            # Perspective push-in then dissolve into the native 3D replay.
            # This is editorial, not a false claim of surveyed scene geometry.
            return Image.blend(sculpture,replay,reveal).convert('RGB')
        if self.full and elapsed>=self.comparison.duration:
            # Keep the exact result card visible before the signature payoff.
            finish=self.path.get('timeline',{}).get('action_seconds',0)
            hold=action_time-finish
            if hold>.8:
                sculpture=self.sculpture(2.5+hold*.08,True)
                # Clear winner in the payoff, not just a decorative canyon.
                d=ImageDraw.Draw(sculpture);winner=min(range(2),key=lambda i:self.comparison.laps[i].lap_time)
                x,y=(28,650) if self.portrait else (560,360)
                d.text((x*self.scale,y*self.scale),self.comparison.laps[winner].code+f' WINS BY {self.gap:.3f}s' if self.gap>=.0005 else 'DEAD HEAT',
                       font=self.font(round(20*self.scale),True),fill=self.colors[winner])
                return Image.blend(replay,sculpture,ease((hold-.8)/.3)).convert('RGB')
        live=self.state(elapsed)
        for beat in self.story.beats:
            # Readable output-time duration even at 20x or dynamic pacing.
            # Cue at section entry: the final-window beat must not appear only
            # for a few frames immediately before the result hold.
            cue=float(self.comparison.laps[0].time_at_distance(beat['start']))
            timeline=self.path.get('timeline',{})
            source_times=timeline.get('source_times')
            if source_times:
                cue_output=float(np.interp(cue,source_times,np.arange(len(source_times))/timeline['fps']))
            else:
                cue_output=intro+(cue-self.start)/self.path.get('playback_speed',1)
            if self.start<=cue<self.end and cue_output<=output_time<cue_output+1.65 and not live['finished']:
                layer=Image.new('RGBA',self.size);d=ImageDraw.Draw(layer);s=self.scale
                y=225 if self.portrait else 145
                d.rounded_rectangle((26*s,y*s,476*s,(y+49)*s),radius=8*s,fill=(6,13,22,240))
                code=self.comparison.laps[beat['driver']].code
                d.text((38*s,(y+8)*s),f'{code} FINDS {beat["gain"]:.3f}s HERE',font=self.font(round(17*s),True),fill=self.colors[beat['driver']])
                d.text((38*s,(y+32)*s),f'MEASURED SWING · {beat["start"]:.0%}–{beat["end"]:.0%} OF LAP DISTANCE',font=self.font(round(8*s),True),fill='#a4b7c7')
                replay=Image.alpha_composite(replay,layer)
                break
        return replay.convert('RGB')

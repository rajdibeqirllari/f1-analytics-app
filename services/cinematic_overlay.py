"""Compact signature HUD and data-derived hook/payoff, never invented gaps."""
import math
import numpy as np
from PIL import Image,ImageDraw
from services.director_overlay import DirectorTelemetryOverlay,lap_clock,WHITE,MUTED,GREEN
from services.video_branding import LOGO,_sprite
from services.video_minimap import TrackMap


class CinematicTelemetryOverlay(DirectorTelemetryOverlay):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.portrait:
            self.chart_box=(26,643,450,70);self.map_box=(26,724,90,88)
            self.rows=[(126,724,350,41),(126,771,350,41)]
            self.map=TrackMap(self.comparison,self.path,self.map_box,self.scale,self.font,self.colors)
            self.brand_position=(26,832)
            self.brand=_sprite(round(76*self.scale),round(57*self.scale),LOGO.stat().st_mtime_ns)
        self.gap=abs(self.comparison.laps[0].lap_time-self.comparison.laps[1].lap_time)

    def render(self,source,elapsed,output_time=None):
        result=super().render(source,elapsed,output_time).convert('RGBA')
        # Keep the legacy graphics intact for other modes. Cover only our
        # branding's secondary line with a compact, quieter signature footer.
        layer=Image.new('RGBA',self.size);d=ImageDraw.Draw(layer);s=self.scale
        def rect(box,fill,r=9):d.rounded_rectangle(tuple(round(v*s) for v in box),radius=round(r*s),fill=fill)
        def text(x,y,value,size=12,color=WHITE,anchor=None):
            d.text((round(x*s),round(y*s)),str(value),font=self.font(round(size*s),True),fill=color,anchor=anchor)
        timeline=self.path.get('timeline',{});mode=timeline.get('pacing','Constant')
        # Display dynamic pacing honestly instead of showing a fixed 3x label.
        if mode!='Constant':
            rect((365,96,478,118),(8,16,25,245),4);text(472,100,'DYNAMIC · 60 FPS' if self.path.get('output_fps')==60 else 'DYNAMIC PACING',8,GREEN,'ra')
        if output_time is None:output_time=max(0,(elapsed-self.start)/self.path.get('playback_speed',1))
        debug=self.path.get('alignment_debug',False)
        if debug:
            rect((26,54,476,90),(8,16,25,245))
            for x,value,color in ((36,'RAW KNOTS',WHITE),(142,'CAR CURVE','#00c8ff'),(260,'ASPHALT EDGE','#20ff50'),(394,'CAR ROOT','#ffe020')):
                text(x,64,value,8,color)
        if self.portrait and output_time<2 and self.start<.01 and not debug:
            opacity=round(240*min(1,output_time/.18)*min(1,(2-output_time)/.3))
            hook=Image.new('RGBA',self.size);hd=ImageDraw.Draw(hook)
            hd.rounded_rectangle((26*s,54*s,476*s,90*s),radius=8*s,fill=(8,16,25,opacity))
            hd.text((251*s,61*s),f'{self.gap:.3f} SECONDS. WHO WAS FASTER?',
                font=self.font(round(16*s),True),anchor='ma',fill=(244,247,251,opacity))
            layer=Image.alpha_composite(layer,hook);d=ImageDraw.Draw(layer)
        live=self.state(elapsed)
        if not live['finished'] and self.portrait and elapsed>self.start+.4:
            past=self.state(max(self.start,elapsed-.7));change=live['delta']-past['delta']
            if abs(change)>.004:
                gainer=0 if change>0 else 1
                text(465,625,self.comparison.laps[gainer].code+' GAINING',9,self.colors[gainer],'ra')
        if live['finished']:
            x,y,w=(26,600,450) if self.portrait else (250,260,670)
            rect((x,y,x+w,y+211),(8,16,25,248))
            winner=min(range(2),key=lambda i:self.comparison.laps[i].lap_time)
            tie=self.gap<.0005
            text(x+18,y+15,'FINAL RESULT · '+self.comparison.session.upper(),10,MUTED)
            text(x+18,y+40,'DEAD HEAT' if tie else self.comparison.laps[winner].code+' WINS',27,self.colors[winner])
            for row,i in enumerate(sorted(range(2),key=lambda i:self.comparison.laps[i].lap_time)):
                lap=self.comparison.laps[i]
                text(x+18,y+91+row*37,lap.code,18,self.colors[i])
                text(x+w-18,y+91+row*37,lap_clock(lap.lap_time),21,WHITE,'ra')
            text(x+18,y+176,f'FINAL GAP  {self.gap:.3f}s',14,GREEN)
        return Image.alpha_composite(result,layer).convert('RGB')

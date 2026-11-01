"""Resolution-independent 3D telemetry composition and atomic, cancellable encoding."""
from functools import lru_cache
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time

from PIL import Image, ImageDraw, ImageFont
from services.circuits_3d import presentation
from services.car_style import comparison_styles,CAR_ATTRIBUTION
from services.video_branding import add_social_brand

WHITE='#f5f7fa'; MUTED='#a9bac9'; RED='#ff4555'; CYAN='#37d9ee'


@lru_cache(maxsize=64)
def font(size, bold=False):
    paths=[Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/('segoeuib.ttf' if bold else 'segoeui.ttf'),
           Path('/usr/share/fonts/truetype/dejavu')/('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')]
    path=next((p for p in paths if p.is_file()),None)
    return ImageFont.truetype(str(path),size) if path else ImageFont.load_default(size=size)


class TelemetryOverlay:
    def __init__(self,comparison,size,start,end,full,driving_path=None):
        self.comparison=comparison; self.size=size; self.start=start; self.end=end; self.full=full
        self.music_credit=(driving_path or {}).get('music_credit')
        self.portrait=size[1]>size[0]
        self.scale=size[0]/(540 if self.portrait else 960)
        self.circuit=presentation(comparison.year,comparison.event,(driving_path or {}).get('track_source'))
        self.environment_credit=(driving_path or {}).get('environment_credit')
        self.original_glb=(driving_path or {}).get('unmodified_glb',False)
        if self.environment_credit:
            self.circuit.update(backend='original-glb' if self.original_glb else 'adapted-asset',
                credit='Track: Dave (@Tyler_Dave) · listed CC BY 4.0 · original GLB' if self.original_glb else 'Environment: Dave (@Tyler_Dave) · listed CC BY 4.0 · adapted')
        self.colors=[style['display'] for style in comparison_styles(comparison.laps)]
        self.director_overlay=None
        self.night_overlay=None
        if driving_path and driving_path.get('social_director'):
            from services.director_overlay import DirectorTelemetryOverlay
            from services.cinematic_overlay import CinematicTelemetryOverlay
            overlay_class=CinematicTelemetryOverlay if driving_path.get('cinematic_ghost') else DirectorTelemetryOverlay
            if driving_path.get('the_limit'):
                from services.limit_overlay import LimitTelemetryOverlay
                overlay_class=LimitTelemetryOverlay
            self.director_overlay=overlay_class(comparison,size,start,end,full,driving_path,self.colors,font)
        elif driving_path and 'night_chase' in driving_path:
            from services.night_overlay import NightTelemetryOverlay
            self.night_overlay=NightTelemetryOverlay(comparison,size,start,end,full,driving_path,self.colors,font)
        from services.video_minimap import TrackMap
        self.minimap=TrackMap(comparison,driving_path,
                              (354,740,154,138) if self.portrait else (28,350,224,124),self.scale,font,self.colors)

    def render(self,source,elapsed,output_time=None):
        result=self._render(source,elapsed,output_time)
        from services.recorded_music import add_music_credit
        return add_music_credit(result,self.music_credit)

    def _render(self,source,elapsed,output_time=None):
        if self.director_overlay:return self.director_overlay.render(source,elapsed,output_time)
        if self.night_overlay:return self.night_overlay.render(source,elapsed)
        width,height=self.size; s=self.scale
        layer=Image.new('RGBA',self.size); draw=ImageDraw.Draw(layer)
        def xy(x,y): return round(x*s),round(y*s)
        def text(x,y,value,size=14,color=WHITE,bold=False,anchor=None):
            draw.text(xy(x,y),str(value),font=font(max(9,round(size*s)),bold),fill=color,anchor=anchor)
        def line(x1,y1,x2,y2,color,width=1):
            draw.line((*xy(x1,y1),*xy(x2,y2)),fill=color,width=max(1,round(width*s)))
        for y in range(min(height,round((255 if self.portrait else 110)*s))):
            alpha=round(247*(1-y/((255 if self.portrait else 110)*s))**.38)
            draw.line((0,y,width,y),fill=(7,13,22,alpha))
        bottom=780 if self.portrait else 430
        bottom_px=round(bottom*s)
        for y in range(bottom_px,height):
            draw.line((0,y,width,y),fill=(7,13,22,round(235*((y-bottom_px)/max(1,height-bottom_px))**.35)))
        line(28,30,43,30,RED,5)
        text(54,19,'RACE HYPE',17,bold=True)
        text(28,51,self.circuit['name'].upper(),28,bold=True)
        text(29,87,f'{self.comparison.year} {self.comparison.session.upper()}  /  LAP COMPARISON',11,MUTED)
        states=[]
        for index,lap in enumerate(self.comparison.laps):
            state=lap.at(elapsed); states.append(state)
            color=self.colors[index]
            x=28+index*260 if self.portrait else 28
            y=118 if self.portrait else 128+index*110
            draw.rounded_rectangle((*xy(x,y),*xy(x+224,y+90)),radius=round(9*s),
                                   fill=(12,20,30,235),outline=(56,70,84,170),width=max(1,round(s)))
            line(x+13,y+12,x+13,y+34,color,3)
            text(x+23,y+9,lap.code,22,bold=True)
            text(x+207,y+16,f'L{lap.number}',12,MUTED,anchor='ra')
            speed='—' if state['finished'] else round(state['speed'])
            text(x+14,y+38,speed,25,bold=True)
            text(x+75,y+54,'KM/H',9,MUTED)
            text(x+145,y+49,'GEAR',9,MUTED)
            gear='—' if state['finished'] or any('nGear is unavailable' in w for w in lap.warnings) else state['gear']
            text(x+203,y+37,gear,25,color,True,anchor='ra')
            throttle_available=not state['finished'] and not any('Throttle is unavailable' in w for w in lap.warnings)
            brake_available=not state['finished'] and not any('Brake is unavailable' in w for w in lap.warnings)
            throttle=max(0,min(100,state['throttle'])) if throttle_available else 0
            braking=brake_available and state['brake']
            text(x+14,y+69,'Throttle',8,MUTED)
            text(x+210,y+69,'Brake',
                 8,RED if braking else MUTED,anchor='ra')
            line(x+14,y+84,x+136,y+84,(49,64,78,255),3)
            if throttle>0:
                line(x+14,y+84,x+14+122*throttle/100,y+84,'#22e66f',3)
            # Source Brake is boolean, not brake pressure: no invented percentage.
            line(x+150,y+84,x+210,y+84,RED if braking else (49,64,78,255),3)
        progress=min(state['progress'] for state in states)
        delta=self.comparison.delta_at(progress)
        winner=self.comparison.laps[0 if delta>=0 else 1].code
        finished=self.full and elapsed>=self.comparison.duration
        y=813 if self.portrait else 428
        x=28 if self.portrait else 290
        text(x,y,'LAP RESULT' if finished else 'TIME GAIN  /  MATCHED DISTANCE',11,MUTED)
        text(x,y+20,f'{winner}  {abs(delta):.3f}s',30,self.colors[0 if delta>=0 else 1],True)
        text(28 if self.portrait else 932,868 if self.portrait else 453,f'{elapsed:05.2f}s',
             12 if self.portrait else 20,bold=True,anchor=None if self.portrait else 'ra')
        self.minimap.draw(layer,elapsed)
        timeline=887 if self.portrait else 485
        right=508 if self.portrait else 932
        line(28,timeline,right,timeline,(80,95,112,180),2)
        fraction=min(1,max(0,(elapsed-self.start)/(self.end-self.start)))
        line(28,timeline,28+(right-28)*fraction,timeline,RED,2)
        text(28,timeline+14,'Original GLB track/scenery · telemetry-driven cars' if self.original_glb else 'Adapted Singapore scenery · illustrative modern road' if self.environment_credit else 'Telemetry layout · illustrative kerbs · telemetry grade / flat fallback'
             if self.circuit['backend']=='telemetry' else 'Real lap timing · generic cars · separated ghost paths',10,MUTED)
        text(28,timeline+35,self.circuit['credit'],9,MUTED)
        if self.environment_credit:text(28,timeline+46,'Concept car: Qvist_designs · CC BY 4.0 · modified',8,MUTED)
        return add_social_brand(Image.alpha_composite(source.convert('RGBA'),layer).convert('RGB'),portrait_height=98)


def encode_frames(comparison,folder,destination,*,size,fps,start,end,frames,full,
                  progress_callback=None,cancelled=None,driving_path=None,producer_done=None,discard_frames=False,require_ready=False,
                  playback_speed=1):
    folder=Path(folder); destination=Path(destination)
    if producer_done is None:
        paths=sorted(folder.glob('frame_*.png'),key=lambda path:int(path.stem.rsplit('_',1)[1]))
        if len(paths)!=frames or any(p.name!=f'frame_{i+1:04d}.png' for i,p in enumerate(paths)):
            raise RuntimeError('Blender produced an incomplete frame sequence. No partial video was published.')
    else:
        paths=[folder/f'frame_{i+1:04d}.png' for i in range(frames)]
    pending=destination.with_suffix('.partial.mp4')
    if driving_path is not None:
        driving_path={**driving_path,'playback_speed':playback_speed}
    overlay=TelemetryOverlay(comparison,size,start,end,full,driving_path)
    credit=CAR_ATTRIBUTION
    credit+=f'; Native offline scene cadence {fps} FPS; pacing '+str((driving_path or {}).get('timeline',{}).get('pacing','Constant'))
    if driving_path and driving_path.get('environment_credit'):
        credit+='; '+driving_path['environment_credit']+'; '+driving_path['environment_source']
    command=['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24',
             '-s',f'{size[0]}x{size[1]}','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264',
             '-crf','18','-preset','fast','-pix_fmt','yuv420p','-fps_mode','passthrough','-movflags','+faststart',
             '-metadata','comment='+credit,str(pending)]
    process=None
    with tempfile.TemporaryFile() as errors:
        try:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            for number,path in enumerate(paths):
                if cancelled and cancelled(): raise InterruptedError('3D generation cancelled.')
                timeline=(driving_path or {}).get('timeline')
                elapsed=timeline['source_times'][number] if timeline else min(end,start+number*playback_speed/fps)
                # Blender and this worker can overlap. A file appearing is not
                # enough: fully decode it before accepting it as a ready frame.
                while True:
                    if cancelled and cancelled():raise InterruptedError('3D generation cancelled.')
                    try:
                        if require_ready and not path.with_suffix('.ready').is_file():
                            raise FileNotFoundError('Frame is still being written.')
                        with Image.open(path) as image:
                            image.load();source=image.copy()
                        break
                    except (OSError,SyntaxError,ValueError):
                        if producer_done is None or producer_done.is_set():
                            raise RuntimeError('Blender produced an incomplete frame sequence. No partial video was published.')
                        time.sleep(.05)
                composed=overlay.render(source,elapsed,number/fps)
                process.stdin.write(composed.tobytes())
                if discard_frames:
                    path.unlink(missing_ok=True)
                    path.with_suffix('.ready').unlink(missing_ok=True)
                if progress_callback and number%max(1,fps//2)==0:
                    progress_callback(.85+.14*(number+1)/frames,'Composing telemetry and encoding MP4')
            process.stdin.close()
            if process.wait(timeout=120):
                errors.seek(0); raise RuntimeError('3D encoding failed: '+errors.read().decode(errors='replace')[-1200:])
            if producer_done is not None:
                while not producer_done.wait(.05):
                    if cancelled and cancelled():raise InterruptedError()
            if cancelled and cancelled(): raise InterruptedError()
            pending.replace(destination)
        finally:
            if process is not None and process.poll() is None:
                process.kill(); process.wait(timeout=20)
            if process is not None and process.stdin is not None and not process.stdin.closed:
                try: process.stdin.close()
                except BrokenPipeError: pass
            pending.unlink(missing_ok=True)

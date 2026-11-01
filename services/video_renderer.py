"""Deterministic Pillow renderer and bounded, background FFmpeg export jobs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import math
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from services.video_comparison import Comparison, VideoSelection, build_comparison
from services.video_branding import add_social_brand
from services.video_timeline import validate_playback_speed, source_elapsed, frame_count


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "video_studio"
INK = "#0b1119"
MUTED = "#8b9eaf"
WHITE = "#eef5fa"
CYAN = "#63f3d1"
RED = "#ff655e"


def lap_clock(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    minutes, remainder = divmod(milliseconds, 60000)
    return f"{minutes}:{remainder / 1000:06.3f}"


class ComparisonRenderer:
    """The exact same composition is used for previews, stills and exports."""
    def __init__(self, comparison: Comparison, size=(720, 1280), camera="Follow cars",music_credit=None):
        self.comparison = comparison
        self.width, self.height = size
        self.scale = self.width / 1080
        self.camera = camera
        self.music_credit=music_credit
        self.portrait = self.height > self.width
        self.fonts = {}
        if self.portrait:
            self.cards = [(0.05, 0.105, 0.435, 0.14), (0.515, 0.105, 0.435, 0.14)]
            self.map_rect = (0.05, 0.267, 0.90, 0.445)
            self.delta_rect = (0.05, 0.731, 0.90, 0.075)
            self.graph_rect = (0.05, 0.829, 0.90, 0.115)
        else:
            self.cards = [(0.035, 0.185, 0.225, 0.245), (0.035, 0.45, 0.225, 0.245)]
            self.map_rect = (0.28, 0.185, 0.685, 0.51)
            self.delta_rect = (0.035, 0.725, 0.225, 0.205)
            self.graph_rect = (0.28, 0.725, 0.685, 0.205)
        self.map_box = self.box(self.map_rect)
        self.graph_box = self.box(self.graph_rect)
        self.base = self._background()

    def box(self, fractions):
        x, y, w, h = fractions
        return (int(x*self.width), int(y*self.height), int((x+w)*self.width), int((y+h)*self.height))

    def font(self, size, bold=False):
        size = max(8, round(size * self.scale))
        key = size, bold
        if key not in self.fonts:
            windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            candidates = [windows / ("segoeuib.ttf" if bold else "segoeui.ttf"),
                          Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
            path = next((path for path in candidates if path.is_file()), None)
            self.fonts[key] = ImageFont.truetype(str(path), size) if path else ImageFont.load_default(size=size)
        return self.fonts[key]

    def text(self, draw, xy, text, size=20, fill=WHITE, bold=False, anchor=None):
        draw.text(xy, str(text), font=self.font(size, bold), fill=fill, anchor=anchor)

    def fit_text(self, draw, xy, text, max_width, size=23, bold=False, fill=WHITE):
        font = self.font(size, bold)
        text = str(text)
        while len(text) > 2 and draw.textlength(text, font=font) > max_width:
            text = text[:-2] + "…"
        draw.text(xy, text, font=font, fill=fill)

    def panel(self, draw, box):
        draw.rounded_rectangle(box, radius=max(5, int(14*self.scale)), fill="#101c29", outline="#243747", width=1)

    def _background(self):
        image = Image.new("RGB", (self.width, self.height), INK)
        draw = ImageDraw.Draw(image)
        s = self.scale
        self.text(draw, (self.width*.05, self.height*.025), "/// RACE HYPE", 23, bold=True)
        self.fit_text(draw, (self.width*.05, self.height*.057), self.comparison.event.upper(), self.width*.65, 34, True)
        self.text(draw, (self.width*.05, self.height*.083 if self.portrait else self.height*.125),
                  f"{self.comparison.year}  /  {self.comparison.session.upper()}  /  SYNCHRONIZED LAP START", 16, MUTED)
        for card in self.cards:
            self.panel(draw, self.box(card))
        self.panel(draw, self.map_box)
        self.panel(draw, self.box(self.delta_rect))
        self.panel(draw, self.graph_box)
        gx0, gy0, gx1, gy1 = self.graph_box
        pad = int(24*s)
        self.text(draw, (gx0+pad, gy0+int(14*s)), "SPEED / MATCHING TRACK DISTANCE", 16, MUTED)
        self.graph_area = (gx0+pad, gy0+int(49*s), gx1-pad, gy1-int(27*s))
        x0,y0,x1,y1 = self.graph_area
        for i in range(4):
            y = y1-(y1-y0)*i/3
            draw.line((x0,y,x1,y), fill="#213241", width=1)
        self.display_colors = [self.comparison.laps[0].color, self.comparison.laps[1].color]
        if self.display_colors[0].lower() == self.display_colors[1].lower():
            self.display_colors[1] = "#faf2ae"
        for i, lap in enumerate(self.comparison.laps):
            data = lap.samples
            points = [(x0 + float(p)*(x1-x0), y1-min(360,max(0,float(v)))/360*(y1-y0))
                      for p,v in zip(data["progress"], data["speed"])]
            draw.line(points, fill=self.display_colors[i], width=max(1,int(2*s)))
        self.text(draw, (x0,y1+int(7*s)), "START", 12, MUTED)
        self.text(draw, (x1,y1+int(7*s)), "FINISH", 12, MUTED, anchor="ra")
        self.text(draw, (self.width*.05,self.height*(.962 if self.portrait else .948)), "GHOST LAPS • PATHS OFFSET FOR CLARITY", 14 if self.portrait else 11, MUTED)
        self.text(draw, (self.width*.05,self.height*(.979 if self.portrait else .975)), "DISTANCE DELTA IS INTERPOLATED • SOURCE: FASTF1", 12 if self.portrait else 10, MUTED)
        return add_social_brand(image)

    def _world(self, progress):
        p = self.comparison.point(progress)[:2]
        prev = self.comparison.point(max(0,progress-.003))[:2]
        nxt = self.comparison.point(min(1,progress+.003))[:2]
        tangent = nxt-prev
        tangent /= max(.001,np.linalg.norm(tangent))
        return p, tangent

    def _draw_track(self, image, elapsed, states):
        x0,y0,x1,y1 = self.map_box
        w,h = x1-x0,y1-y0
        layer = Image.new("RGB", (w,h), "#0c1520")
        d = ImageDraw.Draw(layer)
        step = max(16,int(40*self.scale))
        for x in range(0,w,step): d.line((x,0,x,h),fill="#13202d")
        for y in range(0,h,step): d.line((0,y,w,y),fill="#13202d")
        points = self.comparison.track[:,1:3]
        progress = sum(state["progress"] for state in states)/2
        center,tangent = self._world(progress)
        if self.camera == "Full circuit":
            center = (points.min(axis=0)+points.max(axis=0))/2
            tangent = np.array([0.,1.])
            span = np.maximum(points.max(axis=0)-points.min(axis=0),1)
            factor = min((w-60*self.scale)/span[0], (h-120*self.scale)/span[1])
        else:
            a = self.comparison.point(states[0]["progress"])[:2]
            b = self.comparison.point(states[1]["progress"])[:2]
            # Bounded widening keeps both cars visible when their laps diverge.
            span = max(155, float(np.linalg.norm(a-b))*2.5)
            factor = min(w,h)/span
        right = np.array([tangent[1],-tangent[0]])
        def project(p):
            relative=np.asarray(p)-center
            return (float(w/2+np.dot(relative,right)*factor),float(h*.53-np.dot(relative,tangent)*factor))
        path=[project(p) for p in points]
        road_width=max(5,int(16*factor))
        d.line(path,fill="#667689",width=road_width+max(2,int(2*self.scale)),joint="curve")
        d.line(path,fill="#253444",width=road_width,joint="curve")
        # Reference racing line is a visual guide, not a surveyed circuit model.
        d.line(path,fill="#3b4f60",width=max(1,int(self.scale)),joint="curve")
        for i,(lap,state) in enumerate(zip(self.comparison.laps,states)):
            offset = -2.7 if i==0 else 2.7
            color=self.display_colors[i]
            trail=[]
            times=np.linspace(max(0,min(elapsed,lap.lap_time)-1.4),min(elapsed,lap.lap_time),28)
            for trail_progress in lap.progress_at(times):
                p,tan=self._world(trail_progress)
                normal=np.array([tan[1],-tan[0]])
                trail.append(project(p+normal*offset))
            if len(trail)>1:
                d.line(trail,fill=color,width=max(2,int(3*self.scale)),joint="curve")
            p,tan=self._world(state["progress"])
            normal=np.array([tan[1],-tan[0]])
            position=project(p+normal*offset)
            nose=project(p+normal*offset+tan*3)
            direction=np.array(nose)-np.array(position)
            direction/=max(.001,np.linalg.norm(direction))
            perpendicular=np.array([-direction[1],direction[0]])
            car_scale=max(3.0,6.0*self.scale)
            def car_point(x,y):
                point=np.array(position)+perpendicular*x*car_scale+direction*y*car_scale
                return tuple(point)
            # An original top-down single-seater silhouette, not a side PNG.
            for wx in (-1.15,1.15):
                for wy in (-1.5,1.5):
                    d.polygon([car_point(wx-.37,wy-.6),car_point(wx+.37,wy-.6),car_point(wx+.37,wy+.6),car_point(wx-.37,wy+.6)],fill="#060b11",outline="#8295a5")
            d.polygon([car_point(-.7,-2.5),car_point(.7,-2.5),car_point(.65,1.3),car_point(.25,2.6),car_point(-.25,2.6),car_point(-.65,1.3)],fill=color,outline=WHITE)
            d.line([car_point(-1.8,2.2),car_point(1.8,2.2)],fill=WHITE,width=max(1,int(2*self.scale)))
            d.line([car_point(-1.4,-2.3),car_point(1.4,-2.3)],fill=color,width=max(2,int(3*self.scale)))
            lx,ly=position[0]+15*self.scale,position[1]-18*self.scale
            self.text(d,(lx,ly),lap.code,18,color,True)
        # Start/finish marker and compact track inset.
        p,tan=self._world(0)
        normal=np.array([tan[1],-tan[0]])
        d.line([project(p-normal*8),project(p+normal*8)],fill=WHITE,width=max(1,int(2*self.scale)))
        pad=int(20*self.scale)
        self.text(d,(pad,pad),"GHOST COMPARISON",16,CYAN,True)
        self.text(d,(w-pad,pad),lap_clock(elapsed),23,WHITE,True,anchor="ra")
        mw,mh=int(w*.20),int(h*.21)
        mx,my=w-mw-pad,h-mh-pad
        d.rounded_rectangle((mx-8,my-8,mx+mw+8,my+mh+8),radius=6,fill="#0b1521",outline="#274151")
        lo,hi=points.min(axis=0),points.max(axis=0)
        fac=min(mw/max(1,hi[0]-lo[0]),mh/max(1,hi[1]-lo[1]))
        def mini(p): return (mx+mw/2+(p[0]-(hi[0]+lo[0])/2)*fac,my+mh/2-(p[1]-(hi[1]+lo[1])/2)*fac)
        d.line([mini(p) for p in points],fill="#506d80",width=max(1,int(2*self.scale)))
        for i,state in enumerate(states):
            px,py=mini(self.comparison.point(state["progress"])[:2])
            r=max(2,int(4*self.scale))
            d.ellipse((px-r,py-r,px+r,py+r),fill=self.display_colors[i])
        image.paste(layer,(x0,y0))

    def render(self,elapsed:float)->Image.Image:
        result=self._render(elapsed)
        from services.recorded_music import add_music_credit
        return add_music_credit(result,self.music_credit)

    def _render(self, elapsed: float) -> Image.Image:
        elapsed=float(np.clip(elapsed,0,self.comparison.duration))
        image=self.base.copy()
        draw=ImageDraw.Draw(image)
        states=[lap.at(elapsed) for lap in self.comparison.laps]
        s=self.scale
        for i,(lap,state,rect) in enumerate(zip(self.comparison.laps,states,self.cards)):
            x0,y0,x1,y1=self.box(rect)
            # Cards scale to their own height, not the landscape canvas width.
            cs=min(s,(y1-y0)/268)
            q=cs/s
            pad=int(22*cs)
            color=self.display_colors[i]
            draw.line((x0+pad,y0+pad,x0+pad,y1-pad),fill=color,width=max(2,int(4*cs)))
            left=x0+pad+int(14*cs)
            self.text(draw,(left,y0+pad),lap.code,31*q,color,True)
            self.text(draw,(x1-pad,y0+pad),f"LAP {lap.number}",16*q,MUTED,anchor="ra")
            self.fit_text(draw,(left,y0+int(64*cs)),lap.name,x1-pad-left,19*q)
            self.text(draw,(left,y0+int(96*cs)),f"{round(state['speed']):03d}",48*q,WHITE,True)
            self.text(draw,(left+int(113*cs),y0+int(117*cs)),"KM/H",14*q,MUTED)
            self.text(draw,(x1-pad,y0+int(113*cs)),f"G{state['gear']}" if not any("nGear is unavailable" in w for w in lap.warnings) else "G—",22*q,color,True,anchor="ra")
            bar_y=y1-int(63*cs)
            draw.rounded_rectangle((left,bar_y,x1-pad,bar_y+max(2,int(5*cs))),radius=2,fill="#263849")
            if not any("Throttle is unavailable" in w for w in lap.warnings):
                draw.rounded_rectangle((left,bar_y,left+(x1-pad-left)*state["throttle"]/100,bar_y+max(2,int(5*cs))),radius=2,fill=CYAN)
            self.text(draw,(left,bar_y+int(12*cs)),"THR —" if any("Throttle is unavailable" in w for w in lap.warnings) else f"THR {round(state['throttle'])}%",13*q,MUTED)
            self.text(draw,(x1-pad,bar_y+int(12*cs)),"BRK —" if any("Brake is unavailable" in w for w in lap.warnings) else "BRAKE" if state["brake"] else "BRAKE OFF",13*q,RED if state["brake"] else MUTED,anchor="ra")
            self.text(draw,(left,y1-int(25*cs)),("FINISHED " if state["finished"] else "LAP TIME ")+lap_clock(state["elapsed"]),14*q,color if state["finished"] else MUTED)
        self._draw_track(image,elapsed,states)
        draw=ImageDraw.Draw(image)
        progress=states[0]["progress"]
        delta=self.comparison.delta_at(progress)
        x0,y0,x1,y1=self.box(self.delta_rect)
        pad=int(24*s)
        self.fit_text(draw,(x0+pad,y0+int(15*s)),"TIME GAIN AT MATCHING DISTANCE",x1-x0-2*pad,15 if self.portrait else 11,fill=MUTED)
        leader=self.comparison.laps[0 if delta>=0 else 1].code
        if self.portrait:
            self.text(draw,(x0+pad,y0+int(48*s)),f"{leader}  {abs(delta):.3f}s",40,CYAN if delta>=0 else self.display_colors[1],True)
            self.text(draw,(x1-pad,y0+int(66*s)),"AHEAD" if abs(delta)>.0005 else "LEVEL",16,MUTED,anchor="ra")
        else:
            self.text(draw,(x0+pad,y0+int(50*s)),f"{leader}  {abs(delta):.3f}s",29,CYAN,True)
        gx0,gy0,gx1,gy1=self.graph_area
        x=gx0+progress*(gx1-gx0)
        draw.line((x,gy0,x,gy1),fill=WHITE,width=max(1,int(s)))
        for i,lap in enumerate(self.comparison.laps):
            time_at=lap.time_at_distance(progress)
            speed=lap.at(time_at)["speed"]
            y=gy1-min(360,max(0,speed))/360*(gy1-gy0)
            r=max(2,int(4*s))
            draw.ellipse((x-r,y-r,x+r,y+r),fill=self.display_colors[i],outline=WHITE)
        if elapsed>=self.comparison.duration:
            mx0,my0,mx1,my1=self.map_box
            banner=(mx0+int(30*s),my0+int(65*s),mx1-int(30*s),my0+int(185*s))
            draw.rounded_rectangle(banner,radius=8,fill="#0b1724",outline="#3e6575")
            for i,lap in enumerate(self.comparison.laps):
                self.text(draw,(banner[0]+int(20*s),banner[1]+int((20+45*i)*s)),f"{lap.code}   {lap_clock(lap.lap_time)}",26,self.display_colors[i],True)
        return image


def render_mp4(comparison: Comparison, destination: Path, *, size=(720,1280), fps=30,
               camera="Follow cars", start=0.0, end=None, progress_callback=None, cancelled=None,
               playback_speed=1,music_credit=None) -> Path:
    playback_speed=validate_playback_speed(playback_speed)
    if fps not in (24,30,60):
        raise ValueError("Choose 24, 30 or 60 fps.")
    if any(value < 64 or value % 2 for value in size):
        raise ValueError("Video dimensions must be even and at least 64 pixels.")
    end=comparison.duration if end is None else min(comparison.duration,float(end))
    start=max(0,float(start))
    if end<=start:
        raise ValueError("The video range must contain some of the lap.")
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    renderer=ComparisonRenderer(comparison,size,camera,music_credit=music_credit)
    count=frame_count(start,end,fps,playback_speed,hold=True)  # exact finish plus a real-time 2s result hold
    pending=destination.with_suffix(".partial.mp4")
    command=["ffmpeg","-hide_banner","-loglevel","error","-y","-f","rawvideo","-pix_fmt","rgb24",
             "-s",f"{size[0]}x{size[1]}","-r",str(fps),"-i","pipe:0","-an","-c:v","libx264",
             "-preset","veryfast","-crf","20","-pix_fmt","yuv420p","-movflags","+faststart",str(pending)]
    process=None
    with tempfile.TemporaryFile() as errors:
        try:
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=errors)
            for i in range(count):
                if cancelled and cancelled():
                    raise InterruptedError("Video generation cancelled.")
                frame=renderer.render(source_elapsed(i,start,end,fps,playback_speed))
                process.stdin.write(frame.tobytes())
                if progress_callback and (i%max(1,fps//2)==0 or i==count-1):
                    progress_callback((i+1)/count)
            process.stdin.close()
            result=process.wait(timeout=120)
            if result:
                errors.seek(0)
                raise RuntimeError("Video encoding failed: "+errors.read().decode(errors="replace")[-1500:])
            pending.replace(destination)
        except Exception as exc:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()
            if process is not None and process.stdin is not None and not process.stdin.closed:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass
            pending.unlink(missing_ok=True)
            if isinstance(exc,FileNotFoundError):
                raise RuntimeError("FFmpeg is required to export videos and was not found.") from exc
            if isinstance(exc,BrokenPipeError):
                errors.seek(0)
                raise RuntimeError("Video encoding failed: "+errors.read().decode(errors="replace")[-1500:]) from exc
            raise
    return destination


@dataclass
class VideoJob:
    id: str
    status: str = "queued"
    progress: float = 0.0
    message: str = "Waiting for the renderer"
    error: str = ""
    result: Path | None = None
    comparison: Comparison | None = None
    style: str = "2D"
    start: float = 0.0
    end: float | None = None
    environment: str = "Auto"
    quality: str = "Fast"
    playback_speed: float = 1.0
    pacing: str = 'Constant'
    target_duration: float = 35.
    camera_options: dict = field(default_factory=dict)
    fps: int = 24
    audio: str = 'The Duel'
    audio_volume: float = 80.
    cancelled: threading.Event = field(default_factory=threading.Event)
    created: float = field(default_factory=time.monotonic)


class VideoJobs:
    """Single render worker prevents concurrent exports exhausting the machine."""
    def __init__(self):
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix="race-video")
        self.jobs={}
        self.lock=threading.Lock()

    def submit(self, selection: VideoSelection, *, comparison=None, size=(540,960), fps=24, camera="Follow cars", preview=True,
               style="2D", start=0.0, end=None, environment="Auto",quality="Fast",playback_speed=1,
               pacing='Constant',target_duration=35,camera_options=None,audio='The Duel',audio_volume=80):
        from services.cinematic_timeline import validate_options
        from services.duel_audio import validate_audio
        audio,audio_volume=validate_audio(audio,audio_volume)
        camera_options=validate_options(pacing,target_duration,camera_options)
        if style!='3D' and pacing!='Constant':raise ValueError('Dynamic cinematic pacing requires 3D.')
        if fps not in (24,30,60):raise ValueError('Choose 24, 30 or 60 fps.')
        playback_speed=validate_playback_speed(playback_speed)
        if style not in {"2D","3D"}: raise ValueError("Choose 2D or 3D rendering.")
        if style=="3D":
            from services.video_3d import availability
            if camera not in ('Follow cars','Full circuit','Night chase A','Night chase B','Onboard ghost A','Onboard ghost B','Social director','Cinematic Ghost Chase','Classic Broadcast','The Limit'):
                raise ValueError(f"Unsupported 3D camera: {camera!r}. Select the chase driver again.")
            ready,reason=availability(selection.year,selection.event,environment=environment)
            if not ready: raise ValueError(reason)
        with self.lock:
            # Remove old completed metadata; preserve every exported MP4.
            for key,old in list(self.jobs.items()):
                if old.status in {"complete","failed","cancelled"} and time.monotonic()-old.created>3600:
                    del self.jobs[key]
            if sum(job.status in {"queued","building","rendering"} for job in self.jobs.values())>=4:
                raise ValueError("The render queue is full. Wait for a video to finish.")
            job=VideoJob(uuid.uuid4().hex,style=style,start=start,end=end,environment=environment,quality=quality,
                         playback_speed=playback_speed,pacing=pacing,target_duration=float(target_duration),camera_options=camera_options,fps=fps,
                         audio=audio,audio_volume=audio_volume)
            self.jobs[job.id]=job
        self.executor.submit(self._run,job,selection,comparison,size,fps,camera,preview)
        return job.id

    def snapshot(self,job_id):
        with self.lock:
            job=self.jobs.get(job_id)
            if job is None: return None
            return {key:getattr(job,key) for key in ("id","status","progress","message","error","result","comparison","style","start","end","playback_speed","pacing","fps","audio","audio_volume")}

    def cancel(self,job_id):
        with self.lock:
            if job_id in self.jobs: self.jobs[job_id].cancelled.set()

    def _update(self,job,**fields):
        with self.lock:
            for key,value in fields.items(): setattr(job,key,value)

    def _run(self,job,selection,comparison,size,fps,camera,preview):
        try:
            self._update(job,fps=fps)
            if job.cancelled.is_set(): raise InterruptedError()
            self._update(job,status="building",message="Loading and synchronizing the selected laps")
            comparison=comparison or build_comparison(selection)
            self._update(job,comparison=comparison,status="rendering",message="Preparing the 3D scene" if job.style=="3D" else
                         ("Rendering the full lap preview" if preview else "Rendering the export"))
            label=("night_" if camera in ('Night chase A','Night chase B') else "3d_") if job.style=="3D" else ""
            path=OUTPUT/f"{selection.year}_{selection.driver_a}_{selection.driver_b}_{label}{job.id[:12]}_{'preview' if preview else 'export'}.mp4"
            from services.recorded_music import music_info
            credit=music_info(job.audio)
            if job.style=="3D":
                from services.video_3d import render_3d_mp4
                render_3d_mp4(comparison,path,size=size,fps=fps,camera=camera,start=job.start,end=job.end,
                              environment=job.environment,
                              quality=job.quality,
                              playback_speed=job.playback_speed,
                              pacing=job.pacing,target_duration=job.target_duration,camera_options=job.camera_options,
                              music_credit=credit,
                              progress_callback=lambda value,message:self._update(job,progress=value*(.9 if job.audio!='Silent' else 1),message=message),
                              cancelled=job.cancelled.is_set)
            else:
                render_mp4(comparison,path,size=size,fps=fps,camera=camera,start=job.start,end=job.end,
                           playback_speed=job.playback_speed,music_credit=credit,
                           progress_callback=lambda value:self._update(job,progress=value*(.9 if job.audio!='Silent' else 1)),cancelled=job.cancelled.is_set)
            if job.audio!='Silent':
                from services.duel_audio import attach_duel,soundtrack_timeline
                self._update(job,progress=.92,message='Mixing published instrumental · adaptive timing accents · video quality unchanged')
                timeline,full=soundtrack_timeline(comparison,fps=fps,start=job.start,end=job.end,
                    playback_speed=job.playback_speed,pacing=job.pacing,target_duration=job.target_duration,camera=camera,style=job.style)
                try:
                    attach_duel(comparison,path,path,timeline,full=full,volume=job.audio_volume,cancelled=job.cancelled.is_set,soundtrack=job.audio)
                except BaseException:
                    # This UUID-named file belongs only to this failed job;
                    # never leave a silent export labelled as an audio export.
                    path.unlink(missing_ok=True)
                    raise
            self._update(job,status="complete",progress=1.0,result=path,message="Video + instrumental ready" if job.audio!='Silent' else "Video ready")
        except InterruptedError:
            self._update(job,status="cancelled",message="Generation cancelled")
        except Exception as exc:
            self._update(job,status="failed",error=str(exc),message="Video generation failed")

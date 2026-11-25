from datetime import datetime
from pathlib import Path
import json
import os
import re
from urllib.parse import urlparse
from uuid import uuid4

import fastf1
import pandas as pd
from fastapi import FastAPI,HTTPException,Request,UploadFile,File
from fastapi.responses import FileResponse,HTMLResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel,Field,model_validator

from api import engines
from api.files import ROOT,library,resolve,descriptor,approved
from api.jobs import JobQueue
from services.overview_service import get_season_overview
from services.video_renderer import VideoJobs
from services.video_comparison import VideoSelection
from services.video_timeline import validate_playback_speed
from services.replay_service import build_replay_payload,list_replay_cache,clear_replay_cache
from services.radio_service import load_radio_session

app=FastAPI(title='RACE HYPE',version='1.0',docs_url='/api/docs',openapi_url='/api/openapi.json')
queue=JobQueue()
videos=VideoJobs()
video_requests={}
replays={}
radio_sessions={}
# Your footage + telemetry (upload, engine-sound sync, HUD burn-in). Routes must precede the SPA catch-all.
from api import footage
app.include_router(footage.router)
# Live timing (F1's free stream, followed live or replayed).
from api import live
app.include_router(live.router)
(ROOT/'fastf1_cache').mkdir(exist_ok=True)
fastf1.Cache.enable_cache(str(ROOT/'fastf1_cache'))


class Selection(BaseModel):
    year:int=Field(ge=2018,le=datetime.now().year+1)
    event:str=Field(min_length=2,max_length=100)
    session:str=Field(default='Q',pattern=r'^(R|Q|SQ|S|FP1|FP2|FP3)$')
    driver:str=Field(default='',max_length=5)
    driver_b:str=Field(default='',max_length=5)
    lap:int|None=Field(default=None,ge=1,le=500)
    lap_b:int|None=Field(default=None,ge=1,le=500)
    qualifying_part:str=Field(default='All',pattern=r'^(All|Q1|Q2|Q3)$')

    @model_validator(mode='after')
    def _segment_only_in_qualifying(self):
        # Q1/Q2/Q3 means nothing outside qualifying; a leftover value must not filter a race or practice.
        if self.session not in ('Q','SQ'): self.qualifying_part='All'
        return self


class Task(BaseModel):
    kind:str
    selection:Selection
    options:dict=Field(default_factory=dict)


@app.middleware('http')
async def local_origin(request:Request,call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        if not origin_allowed(request.headers.get('origin'),request.headers.get('host')):
            return JSONResponse({'detail':'This local app accepts changes from its own interface only.'},status_code=403)
    return await call_next(request)


LOCAL_HOSTS={'localhost','127.0.0.1','::1'}


def origin_allowed(origin,host):
    """Changes are accepted from the app's own pages only: the Origin must be the address this engine was reached
    on (any port, so a second engine on 8001 works), or the Vite dev server on this machine. Foreign sites are refused."""
    if not origin: return True   # not a browser cross-site request (curl, same-origin navigation)
    parsed=urlparse(origin)
    if parsed.scheme not in ('http','https') or not parsed.hostname: return False
    if host and parsed.netloc.lower()==host.strip().lower(): return True
    target=urlparse('//'+(host or '')).hostname
    return parsed.hostname in LOCAL_HOSTS and target in LOCAL_HOSTS and parsed.port==5173


@app.exception_handler(ValueError)
async def invalid(request,exc):
    return JSONResponse({'detail':str(exc)},status_code=422)


@app.get('/api/health')
def health():
    from services.hud_renderer import ffmpeg_available
    from services.video_3d import blender_executable
    return dict(status='ok',ffmpeg=ffmpeg_available()[0],blender=bool(blender_executable()),
                charts=engines.CHARTS,year=datetime.now().year)


@app.get('/api/calendar/{year}')
def calendar(year:int):
    if not 2018<=year<=datetime.now().year+1: raise HTTPException(422,'Choose a supported season.')
    try: return engines.calendar(year)
    except Exception as exc: raise HTTPException(503,f'Calendar unavailable: {exc}')


@app.get('/api/overview/{year}')
def overview(year:int):
    from ui.constructor_config import constructors_from_standings
    result=get_season_overview(year)
    result['artwork']=constructors_from_standings(result.get('constructor_standings',[])) if year==2026 else []
    return result


@app.post('/api/jobs',status_code=202)
def submit(task:Task):
    s=task.selection;o=task.options
    if task.kind=='video':
        if not s.driver or not s.driver_b or s.driver==s.driver_b:
            raise ValueError('Choose two different drivers from the loaded session.')
        preview=bool(o.get('preview',True))
        style=o.get('style','2D')
        short=int(o.get('resolution',540 if preview else 1080))
        if short not in ((540,720,1080) if preview else (720,1080)): raise ValueError('Unsupported video resolution.')
        fps=int(o.get('fps',24 if preview else 30))
        if fps not in (24,30,60): raise ValueError('Unsupported frame rate.')
        size=(short,short*16//9) if o.get('orientation','portrait')=='portrait' else (short*16//9,short)
        # H.264 requires even dimensions.
        size=tuple(v-v%2 for v in size)
        start=float(o.get('start',0));end=o.get('end')
        if start<0 or (end is not None and (float(end)<=start or float(end)>1200)): raise ValueError('Invalid clip time range.')
        camera=o.get('camera','Follow cars')
        if camera not in ('Follow cars','Full circuit','Night chase A','Night chase B','Onboard ghost A','Onboard ghost B','Social director','Cinematic Ghost Chase','Classic Broadcast','The Limit'): raise ValueError('Choose a supported camera.')
        quality=o.get('quality','Balanced')
        if quality not in ('Fast','Balanced','High'): raise ValueError('Choose a supported finish.')
        playback_speed=validate_playback_speed(o.get('playback_speed',1))
        from services.cinematic_timeline import validate_options
        validate_options(o.get('pacing','Constant'),o.get('target_duration',35),o.get('camera_options'))
        from services.duel_audio import validate_audio
        audio,audio_volume=validate_audio(o.get('audio','The Duel'),o.get('audio_volume',80))
        settings=dict(size=size,fps=fps,camera=camera,preview=preview,style=style,start=start,
                      end=float(end) if end is not None else None,environment='Telemetry-built',quality=quality,
                      playback_speed=playback_speed,pacing=o.get('pacing','Constant'),target_duration=o.get('target_duration',35),
                      camera_options=o.get('camera_options'),audio=audio,audio_volume=audio_volume)
        selection=VideoSelection(s.year,s.event,s.session,s.driver,s.driver_b,s.lap,s.lap_b,s.qualifying_part)
        comparison=None
        previous=o.get('preview_job')
        if previous and previous in video_requests:
            previous_s,_=video_requests[previous]
            if previous_s==selection:
                old=videos.snapshot(previous)
                comparison=old.get('comparison') if old else None
        key=videos.submit(selection,comparison=comparison,**settings)
        video_requests[key]=(selection,settings)
        return {'id':'v_'+key}
    def task_fn(progress):
        if task.kind=='catalog': return engines.catalog(s)
        if task.kind=='timing': return engines.timing(s)
        if task.kind=='traces': return engines.traces(s)
        if task.kind=='chart': return engines.chart(s,o,progress)
        if task.kind=='telemetry': return engines.telemetry(s,o,progress)
        if task.kind=='hud': return engines.hud(s,o,progress)
        if task.kind=='footage_sync': return footage.sync(s,o,progress)
        if task.kind=='footage_render': return footage.render(s,o,progress)
        if task.kind=='replay':
            from services.replay_fallback import replay_with_fallback
            payload=replay_with_fallback(s.year,s.event,s.session,int(o.get('sample_rate',3)),
                       refresh=bool(o.get('refresh',False)),progress_callback=progress,
                       recordings=[ROOT/'outputs'/'live',ROOT/'tmp'])
            token=uuid4().hex;replays[token]=payload
            return {'viewer':f'/api/replays/{token}/viewer','data':f'/api/replays/{token}/data','meta':{k:v for k,v in payload['meta'].items() if k!='cache_file'},
                    'technical':payload['technical']}
        if task.kind=='radio':
            result=load_radio_session(s.year,s.event,s.session,cache_dir=ROOT/'outputs'/'radio'/'cache',
                                     output_dir=ROOT/'outputs'/'radio',force_refresh=bool(o.get('refresh',False)))
            token=uuid4().hex;radio_sessions[token]=result
            clips=[]
            for i,clip in enumerate(result['clips']):
                row={k:v for k,v in clip.items() if k not in ('local_path','recording_url')}
                row['url']=f'/api/radio/{token}/{i}'
                clips.append(row)
            return engines.clean(dict(clips=clips,files=[descriptor(result['csv_path']),descriptor(result['json_path'])]))
        raise ValueError('Unsupported task.')
    if task.kind not in ('catalog','timing','traces','chart','telemetry','hud','replay','radio','footage_sync','footage_render'):
        raise ValueError('Unsupported task.')
    if task.kind=='replay':
        if s.session not in ('R','Q','S','SQ'): raise ValueError('Replays support Race, Qualifying, Sprint and Sprint qualifying.')
        if int(o.get('sample_rate',3)) not in (1,3,5,10): raise ValueError('Choose 1, 3, 5 or 10 replay samples per second.')
    return {'id':queue.submit(task.kind,task_fn)}


@app.get('/api/jobs/{key}')
def job(key:str):
    if key.startswith('v_'):
        data=videos.snapshot(key[2:])
        if not data: raise HTTPException(404,'Render not found. A server restart clears active render metadata; saved files remain in My Downloads.')
        comparison=data.pop('comparison',None)
        path=data.pop('result',None)
        data['id']=key
        from services.recorded_music import music_info
        credit=music_info(data.get('audio','Silent'))
        data['result']=dict(file=descriptor(path),laps=[dict(driver=l.code,name=l.name,lap=l.number,lap_time=l.lap_time) for l in comparison.laps],
                            warnings=comparison.warnings,playback_speed=data['playback_speed'],pacing=data['pacing'],fps=data['fps'],
                            audio=data.get('audio','Silent'),audio_volume=data.get('audio_volume',80),
                            music_credit=credit['attribution'] if credit else None) if path and comparison else None
        return engines.clean(data)
    data=queue.snapshot(key)
    if not data: raise HTTPException(404,'Task not found. Reload the data after restarting the server.')
    return data


@app.post('/api/jobs/{key}/cancel')
def cancel(key:str):
    if key.startswith('v_'): videos.cancel(key[2:])
    else: queue.cancel(key)
    return {'message':'Cancellation requested; an in-flight data download or encoder step may finish first.'}


@app.post('/api/uploads')
async def upload(file:UploadFile=File(...)):
    if not (file.filename or '').lower().endswith('.csv'): raise HTTPException(422,'Choose a CSV file.')
    data=await file.read(10*1024*1024+1)
    if len(data)>10*1024*1024: raise HTTPException(413,'CSV files must be smaller than 10 MB.')
    from io import BytesIO
    try:
        frame=pd.read_csv(BytesIO(data))
        normalized=engines.normalize_telemetry(frame,'Upload CSV')
        if normalized.empty: raise ValueError('No usable samples found.')
    except Exception as exc: raise HTTPException(422,f'CSV could not be read: {exc}')
    folder=ROOT/'outputs'/'uploads';folder.mkdir(parents=True,exist_ok=True)
    key=uuid4().hex;(folder/f'{key}.csv').write_bytes(data)
    return {'id':key,'rows':len(frame),'columns':list(frame.columns)}


@app.get('/api/files')
def files(): return library()


@app.get('/api/files/{key}')
def output_file(key:str,download:bool=False):
    try: path=resolve(key)
    except FileNotFoundError: raise HTTPException(404,'Output not found.')
    return FileResponse(path,filename=path.name if download else None)


@app.get('/api/replays/{key}/viewer',response_class=HTMLResponse)
def replay_viewer(key:str):
    payload=replays.get(key)
    if not payload: raise HTTPException(404,'Reload the replay after restarting the server.')
    folder=ROOT/'components'/'race_replay_web'
    doc=(folder/'index.html').read_text(encoding='utf-8')
    doc=doc.replace('__REPLAY_PAYLOAD__',json.dumps(payload,ensure_ascii=False).replace('<','\\u003c'))
    doc=doc.replace('__REPLAY_CSS__',(folder/'replay.css').read_text(encoding='utf-8'))
    doc=doc.replace('__REPLAY_JS__',(folder/'replay.js').read_text(encoding='utf-8'))
    return HTMLResponse(doc)


@app.get('/api/replays/{key}/data')
def replay_data(key:str):
    """The loaded replay as JSON, for the Race Hype replay page (same frames the classic viewer uses)."""
    from fastapi import Response
    payload=replays.get(key)
    if not payload: raise HTTPException(404,'Reload the replay after restarting the server.')
    body={**payload,'meta':{k:v for k,v in payload['meta'].items() if k!='cache_file'}}
    return Response(json.dumps(body,ensure_ascii=False,separators=(',',':')),media_type='application/json')



# 3D Broadcast on the Replay page: native-rate positions for the loaded replay, on the replay's own clock.
from services.replay_scene import ReplayScenes
_replay_scenes=ReplayScenes()


@app.get('/api/replays/{key}/scene')
def replay_scene(key:str):
    payload=replays.get(key)
    if not payload: raise HTTPException(404,'Reload the replay after restarting the server.')
    return _replay_scenes.describe(key,payload)


@app.get('/api/replays/{key}/radio')
def replay_radio(key:str):
    """Team radio events on the replay clock (OpenF1-built replays), for the 3D Broadcast's radio card."""
    payload=replays.get(key)
    if payload is None: raise HTTPException(404,'Replay not found. Load it again.')
    from services.replay_scene import radio_events
    item=_replay_scenes.get(key,payload)
    if item.get('status')!='ready': return {'events':[],'reason':'The 3D scene is still loading.','loading':True}
    return radio_events(item,payload)


@app.get('/api/replays/{key}/scene/samples')
def replay_scene_samples(key:str,t0:float,t1:float,source:str='auto',step:float=0.25):
    payload=replays.get(key)
    if not payload: raise HTTPException(404,'Reload the replay after restarting the server.')
    if not (t1>t0) or t1-t0>900: raise HTTPException(422,'Ask for a window of up to 15 minutes.')
    try: return _replay_scenes.samples(key,payload,t0,t1)
    except ValueError as exc: raise HTTPException(409,str(exc))

@app.get('/api/replay-cache')
def replay_cache(): return [{'name':p.name,'size':p.stat().st_size} for p in list_replay_cache()]


@app.delete('/api/replay-cache')
def delete_replay_cache(): return {'removed':clear_replay_cache()}


@app.get('/api/radio/{key}/{index}')
def radio_audio(key:str,index:int,download:bool=False):
    result=radio_sessions.get(key)
    if not result or not 0<=index<len(result['clips']): raise HTTPException(404,'Radio clip not found.')
    clip=result['clips'][index]
    local=Path(str(clip.get('local_path') or ''))
    radio_root=(ROOT/'outputs'/'radio').resolve()
    # The radio archive cache is private to the Library, but this page's own player may stream from it.
    if local.is_file() and local.resolve().is_relative_to(radio_root) and local.suffix.lower()=='.mp3':
        return FileResponse(local,media_type='audio/mpeg',filename=local.name if download else None)
    url=clip.get('recording_url','')
    host=urlparse(url).hostname or ''
    if urlparse(url).scheme!='https' or not host.endswith('.formula1.com'):
        raise HTTPException(422,'This recording has no supported downloadable audio URL.')
    import requests
    try:
        response=requests.get(url,timeout=(5,25),allow_redirects=False)
        response.raise_for_status()
        if len(response.content)>32*1024*1024: raise ValueError('Recording exceeds the size limit.')
        folder=ROOT/'outputs'/'radio';folder.mkdir(parents=True,exist_ok=True)
        path=folder/f'{key}_{index}.mp3';path.write_bytes(response.content)
        clip['local_path']=str(path)
        return FileResponse(path,media_type='audio/mpeg',filename=path.name if download else None)
    except Exception as exc: raise HTTPException(502,f'Recording could not be downloaded: {exc}')


# Serve only the artwork used by the interface, never imported 3D source models.
for name in ('flags','f1_2026','logo'):
    folder=ROOT/'assets'/name
    if folder.is_dir(): app.mount(f'/art/{name}',StaticFiles(directory=folder),name=name)
app.mount('/design',StaticFiles(directory=ROOT/'frontend'/'public'/'design'),name='design')
dist=Path(os.environ.get('RACEHYPE_DIST') or ROOT/'frontend'/'dist')   # RACEHYPE_DIST: serve another build (isolated test instances)


class CachedStatic(StaticFiles):
    """Static files with explicit caching. Fingerprinted build chunks (/assets) never change, so browsers may keep
    them for a year; models/decoders revalidate. A missing file is a plain 404 that is never cached, so a tab from an
    older build sees the real failure (and recovers) instead of a cached error or an HTML page posing as a script."""
    def __init__(self,*a,immutable=False,**k):
        super().__init__(*a,**k);self.immutable=immutable
    async def get_response(self,path,scope):
        try:
            r=await super().get_response(path,scope)
        except StarletteHTTPException as exc:          # StaticFiles raises Starlette's class (FastAPI's subclasses it)
            if exc.status_code!=404: raise
            return JSONResponse({'detail':'Not found.'},status_code=404,headers={'Cache-Control':'no-store'})
        if r.status_code==404:
            r.headers['Cache-Control']='no-store'
        elif r.status_code in (200,304):
            r.headers['Cache-Control']='public, max-age=31536000, immutable' if self.immutable else 'no-cache'
        return r


if dist.is_dir():
    app.mount('/assets',CachedStatic(directory=dist/'assets',immutable=True),name='frontend-assets')
    # 3D Broadcast models (venue GLBs, car GLBs, Draco decoder), copied from frontend/public by the build.
    for _sub in ('venues','cars','draco'):
        if (dist/_sub).is_dir(): app.mount(f'/{_sub}',CachedStatic(directory=dist/_sub),name=f'frontend-{_sub}')

_ASSET_EXT=re.compile(r'\.(js|mjs|css|map|json|wasm|glb|png|jpe?g|webp|svg|ico|woff2?|ttf|txt)$',re.I)


@app.get('/{path:path}')
def frontend(path:str):
    if path.startswith(('api/','art/')): raise HTTPException(404,'Not found.')
    # A request for a file (script, style, image…) is never answered with the app's HTML: either the file from the
    # build's root (e.g. favicon) or a real, uncached 404.
    if _ASSET_EXT.search(path):
        f=(dist/path).resolve()
        if dist.resolve() in f.parents and f.is_file(): return FileResponse(f,headers={'Cache-Control':'no-cache'})
        return JSONResponse({'detail':'Not found.'},status_code=404,headers={'Cache-Control':'no-store'})
    index=dist/'index.html'
    if not index.exists(): return JSONResponse({'message':'Build the frontend with npm run build in frontend/, or use Vite on port 5173.'},status_code=503)
    # The HTML names the current entry chunk: always revalidate it so a new build is picked up on the next load.
    return FileResponse(index,headers={'Cache-Control':'no-cache'})

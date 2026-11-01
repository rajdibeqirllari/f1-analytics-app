"""Adapters over existing Python calculations, never over Streamlit page code."""
from functools import lru_cache
from pathlib import Path
from threading import Lock
from uuid import uuid4
import json
import math
import numpy as np
import pandas as pd
from PIL import Image
import fastf1

from api.files import ROOT, descriptor
from services.video_comparison import load_video_session,session_catalog,filtered_laps
from services.export_service import normalize_telemetry,make_after_effects_tsv,make_racerender_csv
from services.openf1_service import load_openf1_lap
from services import analysis_service as analysis

CHARTS={
 'Lap analysis':['Fastest lap map','Telemetry Comparison','Car Pace Delta Map','Sector Performance Heatmap'],
 'Race pace':['Selected driver race pace','Driver lap comparison','Lap consistency','Lap-by-lap pace delta','Lap-by-lap delta + stints'],
 'Strategy':['Stint strategy','Tyre Degradation Analysis','Hard stint average pace','Medium stint average pace'],
 'Race overview':['Position Tracker','Gap to Leader','Team race pace delta','Speed Trap Analysis']}
_plot_lock=Lock()
_session_lock=Lock()


def clean(value):
    if isinstance(value,dict): return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,np.ndarray)): return [clean(v) for v in value]
    if isinstance(value,(pd.Timestamp,pd.Timedelta)): return str(value)
    if isinstance(value,Path): return str(value)
    if value is pd.NA or value is pd.NaT: return None
    if isinstance(value,(float,np.floating)): return float(value) if math.isfinite(value) else None
    if isinstance(value,np.integer): return int(value)
    if isinstance(value,np.bool_): return bool(value)
    return value


def records(frame):
    return clean(frame.to_dict(orient='records'))


def session_for(s):
    # FastF1 writes its disk cache while loading. Share successful in-memory sessions.
    with _session_lock:
        return load_video_session(s.year,s.event,s.session)


@lru_cache(maxsize=12)
def calendar(year):
    frame=fastf1.get_event_schedule(year,include_testing=False)
    if frame.empty: raise ValueError('No event calendar was returned for this season.')
    frame=frame.sort_values('EventDate',kind='stable')
    return records(frame)


def catalog(s):
    with _session_lock:
        return clean(session_catalog(s.year,s.event,s.session))


def timing(s):
    session=session_for(s)
    try:
        # Load these channels once, without reloading laps or telemetry.
        with _session_lock:
            if not getattr(session,'_rh_context_loaded',False):
                session.load(laps=False,telemetry=False,weather=True,messages=True)
                session._rh_context_loaded=True
    except Exception:
        pass
    rows=[]
    def seconds(v):
        return float(v.total_seconds()) if pd.notna(v) and hasattr(v,'total_seconds') else None
    for number in session.drivers:
        info=session.get_driver(number)
        laps=session.laps.pick_drivers(number)
        valid=laps.dropna(subset=['LapTime'])
        last=laps.iloc[-1] if len(laps) else {}
        best=valid.pick_fastest() if len(valid) else {}
        if best is None: best={}
        position=pd.to_numeric(info.get('Position'),errors='coerce')
        rows.append(dict(driver=str(info.get('Abbreviation') or number),number=str(number),
            name=info.get('FullName'),team=info.get('TeamName'),color=info.get('TeamColor'),
            position=int(position) if pd.notna(position) else None,
            time=seconds(info.get('Time')),status=info.get('Status'),
            best=seconds(best.get('LapTime')),last=seconds(last.get('LapTime')),
            s1=seconds(last.get('Sector1Time')),s2=seconds(last.get('Sector2Time')),s3=seconds(last.get('Sector3Time')),
            compound=last.get('Compound'),speed=last.get('SpeedST'),lap=last.get('LapNumber')))
    rows.sort(key=lambda row: row['position'] if row['position'] is not None else 999)
    weather=[]; messages=[]
    for attr,dest in [('weather_data',weather),('race_control_messages',messages)]:
        try: dest.extend(records(getattr(session,attr)))
        except Exception: pass
    track=[]
    try:
        tel=session.laps.pick_fastest().get_telemetry().dropna(subset=['X','Y'])
        track=tel[['X','Y']].iloc[::max(1,len(tel)//700)].values.tolist()
    except Exception: pass
    return clean(dict(rows=rows,weather=weather[-1] if weather else None,messages=messages,track=track,
                     source='FastF1',mode='Historical session classification; lap channels are the last recorded lap.'))


def load_telemetry(s,source='Auto',upload_id=None):
    fallback=None
    if source=='Upload CSV':
        if not upload_id or not __import__('re').fullmatch('[0-9a-f]{32}',upload_id):
            raise ValueError('Upload a CSV first.')
        path=ROOT/'outputs'/'uploads'/f'{upload_id}.csv'
        if not path.is_file(): raise ValueError('Uploaded CSV is no longer available.')
        frame=normalize_telemetry(pd.read_csv(path),'Upload CSV')
        return frame,frame.copy(),dict(source='Upload CSV',driver=s.driver,fallback=None)
    if source in ('FastF1','Auto'):
        try:
            session=session_for(s)
            laps=filtered_laps(session,s.driver,s.qualifying_part)
            lap=laps[laps.LapNumber==s.lap].iloc[0] if s.lap is not None else laps.pick_fastest()
            if lap is None: raise ValueError('No valid timed lap found for this driver.')
            frame=normalize_telemetry(lap.get_telemetry(),'FastF1')
            number=str(session.get_driver(s.driver)['DriverNumber'])
            full=normalize_telemetry(session.car_data[number],'FastF1')
            return frame,full,dict(source='FastF1',driver=s.driver,lap_number=int(lap.LapNumber),fallback=None)
        except Exception as exc:
            if source!='Auto': raise
            fallback=str(exc)
    lap,full,meta,lapmeta=load_openf1_lap(s.year,s.event,s.session,s.driver,'Lap number' if s.lap else 'Fastest',s.lap)
    return lap,full,dict(source='OpenF1',driver=s.driver,lap_number=lapmeta.get('lap_number'),fallback=fallback)


def telemetry(s,options,progress):
    fps=int(options.get('fps',30))
    if fps not in (24,25,30,50,60): raise ValueError('Choose a supported export frame rate.')
    frame,full,meta=load_telemetry(s,options.get('source','Auto'),options.get('upload_id'))
    if frame.empty: raise ValueError('The selected source returned no telemetry samples.')
    progress(.65,'Preparing production export formats')
    folder=ROOT/'outputs'/'telemetry';folder.mkdir(parents=True,exist_ok=True)
    stem=f'{s.year}_{s.driver}_{uuid4().hex[:10]}'
    outputs=[]
    for label,data,ext,sep in [('Selected lap',frame,'csv',','),('Full telemetry',full,'csv',','),
             ('After Effects',make_after_effects_tsv(frame,fps),'tsv','\t'),
             ('RaceRender',make_racerender_csv(frame),'csv',',')]:
        path=folder/f'{stem}_{label.replace(" ","_")}.{ext}'
        data.to_csv(path,index=False,sep=sep)
        outputs.append(dict(label=label,**descriptor(path)))
    return dict(files=outputs,metadata=clean(meta),columns=list(frame.columns),rows=len(frame),
                duration=clean(pd.to_numeric(frame.time_sec,errors='coerce').max()),preview=records(frame.head(250)))


def traces(s):
    try:
        return _fastf1_traces(s)
    except Exception as primary:
        from services.openf1_comparison import comparison
        from services.video_comparison import VideoSelection
        try:
            comp=comparison(VideoSelection(s.year,s.event,s.session,s.driver,s.driver_b,s.lap,s.lap_b,s.qualifying_part))
        except Exception as secondary:
            raise ValueError(f'FastF1 telemetry unavailable: {primary} OpenF1 fallback unavailable: {secondary}') from secondary
        result=[]
        for lap in comp.laps:
            frame=lap.samples.rename(columns={'t':'time_sec','speed':'speed_kmh',
                 'throttle':'throttle_pct','brake':'brake_active','progress':'relative_distance'}).copy()
            t=frame.time_sec.to_numpy();speed=frame.speed_kmh.to_numpy()/3.6
            frame['distance_m']=np.r_[0,np.cumsum((speed[:-1]+speed[1:])*.5*np.diff(t))]
            result.append(dict(driver=lap.code,color=lap.color.lstrip('#'),lap=lap.number,
                lap_time=lap.lap_time,sectors=lap.sectors,source='OpenF1',warnings=lap.warnings,
                points=records(frame.iloc[::max(1,len(frame)//1800)])))
        return clean(result)


def _fastf1_traces(s):
    result=[]
    session=session_for(s)
    for code,lapnum in [(s.driver,s.lap),(s.driver_b,s.lap_b)]:
        laps=filtered_laps(session,code,s.qualifying_part)
        lap=laps[laps.LapNumber==lapnum].iloc[0] if lapnum else laps.pick_fastest()
        if lap is None: raise ValueError(f'No valid lap for {code}.')
        raw=lap.get_telemetry()
        data=normalize_telemetry(raw,'FastF1')
        if 'Distance' in raw: data['distance_m']=raw.Distance.to_numpy()
        info=session.get_driver(code)
        result.append(dict(driver=code,color=str(info.get('TeamColor') or 'ffffff'),
             lap=int(lap.LapNumber),lap_time=lap.LapTime.total_seconds(),
             sectors=[clean(lap.get(f'Sector{i}Time').total_seconds()) if pd.notna(lap.get(f'Sector{i}Time')) else None for i in (1,2,3)],
             points=records(data.iloc[::max(1,len(data)//1800)])))
    return clean(result)


def chart(s,options,progress):
    session=session_for(s)
    name=options.get('chart','Fastest lap map')
    if name not in sum(CHARTS.values(),[]): raise ValueError('Choose a supported analysis.')
    folder=ROOT/'outputs'/'charts';folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'{s.year}_{name.replace(" ","_")}_{uuid4().hex[:8]}.png'
    a,b=s.driver,s.driver_b;drivers=options.get('drivers') or [a,b]
    with _plot_lock:
        analysis.image_format=options.get('image_format','16:9 (YouTube)')
        analysis.COLOR_MODE=options.get('color_mode','FastF1 Official')
        analysis.CUSTOM_COLOR_A=options.get('color_a','#00D2BE');analysis.CUSTOM_COLOR_B=options.get('color_b','#DC0000')
        progress(.6,'Rendering the existing analysis calculation')
        pair={'Fastest lap map':analysis.render_fastest_lap_map,'Driver lap comparison':analysis.render_driver_lap_comparison,
              'Lap-by-lap pace delta':analysis.render_lap_delta,'Lap-by-lap delta + stints':analysis.render_lap_delta_with_stints}
        group={'Sector Performance Heatmap':analysis.render_sector_performance_heatmap,
              'Selected driver race pace':analysis.render_selected_driver_race_pace,'Lap consistency':analysis.render_lap_consistency,
              'Stint strategy':analysis.render_stint_strategy,'Tyre Degradation Analysis':analysis.render_tyre_deg_analysis,
              'Position Tracker':analysis.render_position_tracker,'Gap to Leader':analysis.render_gap_to_leader}
        try:
            if name in pair: pair[name](session,a,b,path)
            elif name in group: group[name](session,drivers,path)
            elif name=='Telemetry Comparison': analysis.render_telemetry_comparison(session,s.lap or 10,a,b,path)
            elif name=='Car Pace Delta Map': analysis.render_car_pace_delta_map(session,a,b,path,lap_mode='Same lap number' if s.lap else 'Fastest lap',lap_number=s.lap)
            elif name=='Team race pace delta': analysis.render_team_race_pace_delta(session,path)
            elif name=='Speed Trap Analysis': analysis.render_speed_traps(session,path)
            else: analysis.render_stint_average_pace(session,drivers,'HARD' if name.startswith('Hard') else 'MEDIUM',path)
        finally: analysis.plt.close('all')
    if not path.exists(): raise ValueError('This analysis has no usable samples for the selected session.')
    return dict(file=descriptor(path),chart=name)


def hud(s,options,progress):
    from services.hud_renderer import (normalize_hud_telemetry,build_hud_preview_frame,
        export_hud_alpha_video,export_hud_png_sequence,zip_png_sequence)
    frame,_,meta=load_telemetry(s,options.get('source','Auto'),options.get('upload_id'))
    frame=normalize_hud_telemetry(frame,meta['source'])
    common=dict(canvas_size=(int(options.get('width',1080)),int(options.get('height',1920))),
                hud_width=int(options.get('hud_width',460)),position_preset=options.get('position','Bottom left'),
                custom_x=int(options.get('x',80)),custom_y=int(options.get('y',1180)),hud_year=s.year)
    if any(v<64 or v>3840 for v in common['canvas_size']): raise ValueError('Canvas dimensions must be 64–3840 pixels.')
    if not 100<=common['hud_width']<=1500: raise ValueError('HUD width must be 100–1500 pixels.')
    label=f'{s.driver}_{uuid4().hex[:10]}'
    folder=ROOT/'outputs'/'hud_exports';folder.mkdir(parents=True,exist_ok=True)
    mode=options.get('format','Preview')
    if mode=='Preview':
        rgba,row=build_hud_preview_frame(frame,ROOT/'assets'/'hud',at_time=float(options.get('time',0)),**common)
        path=folder/f'{label}.png';Image.fromarray(rgba).save(path)
        return dict(file=descriptor(path),sample=clean(row),metadata=clean(meta))
    fps=int(options.get('fps',30))
    if fps not in (24,25,30,50,60): raise ValueError('Unsupported frame rate.')
    kw=dict(fps=fps,progress_callback=lambda i,n:progress(.3+.65*i/max(n,1),'Rendering alpha frames'),**common)
    if mode=='PNG Sequence':
        result=export_hud_png_sequence(frame,ROOT/'assets'/'hud',ROOT/'outputs'/'hud_frames',label,**kw)
        path=folder/f'{label}.zip';path.write_bytes(zip_png_sequence(result.frames_dir))
    elif mode in ('WebM VP9 Alpha','MOV ProRes 4444'):
        result=export_hud_alpha_video(frame,ROOT/'assets'/'hud',folder,ROOT/'outputs'/'hud_frames',label,format_label=mode,**kw)
        path=result.output_path
    else: raise ValueError('Unsupported overlay format.')
    return dict(file=descriptor(path),metadata=clean(meta),frames=result.frame_count,duration=result.duration_sec)

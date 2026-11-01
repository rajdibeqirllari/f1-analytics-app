from __future__ import annotations

from datetime import date
import html

import streamlit as st

from services.video_comparison import VideoSelection, session_catalog
from services.video_renderer import VideoJobs, lap_clock
from services.video_3d import availability
from services.car_style import RENDER_VERSION,CAR_SOURCE
from services.video_branding import BRANDING_VERSION
from ui.components import section_title
from ui.race_identity import event_label,track_card,driver_card
from services.circuit_lighting import race_lighting


@st.cache_resource
def video_jobs():
    return VideoJobs()


@st.cache_data(ttl=1800, show_spinner=False)
def catalog(year, event, session):
    return session_catalog(year, event, session)


def _choose_style(value):
    st.session_state['video_render_style']=value


@st.fragment(run_every=1)
def _job_panel():
    state=st.session_state.get("video_job_id")
    if not state: return
    manager=video_jobs()
    job=manager.snapshot(state)
    if not job:
        st.info("This render is no longer in memory. Build another preview.")
        return
    if job["status"] in {"queued","building","rendering"}:
        st.progress(job["progress"],text=job["message"])
        if st.button("Cancel generation",key="video_cancel"):
            manager.cancel(state)
        return
    if job["status"]=="failed":
        if st.session_state.get("video_terminal_job")!=state:
            st.session_state["video_terminal_job"]=state
            st.rerun()
        st.error(job["error"])
        return
    if job["status"]=="cancelled":
        if st.session_state.get("video_terminal_job")!=state:
            st.session_state["video_terminal_job"]=state
            st.rerun()
        st.info("Generation cancelled. You can start a new preview.")
        return
    # Only the first completion triggers a full rerun, enabling export controls.
    if st.session_state.get("video_completed_job")!=state:
        st.session_state["video_completed_job"]=state
        st.session_state["video_result"]=job
        st.rerun()


def render_video_studio(*, latest: dict, event_loader):
    st.markdown('<div class="rh-create-hero"><div><span class="rh-eyebrow">RACE HYPE / THE CREATOR PADDOCK</span>'
                '<h1>Two drivers.<br><em>One story.</em></h1><p>Put their laps head to head. Make a clip worth watching.</p></div>'
                '<div class="rh-hero-stamp"><span>HEAD<br>TO HEAD</span><small>REAL LAPS. YOUR PERSPECTIVE.</small></div></div>',unsafe_allow_html=True)
    if st.session_state.get('video_render_style')=='3D · Night Chase':
        st.session_state['video_render_style']='3D · Chase'
    style_label=st.session_state.get('video_render_style','3D · Chase')
    styles=[('2D · Telemetry','The Breakdown','A bird’s-eye view. Every input, every gain.','⌁'),
            ('3D · Cinematic beta','Trackside','See both cars. Let the lap tell the story.','◈'),
            ('3D · Chase','On Their Tail','Close to the car. Right in the action.','↗')]
    with st.container(key='creative_styles'):
        for column,(value,title,description,icon) in zip(st.columns(3),styles):
            with column:
                selected=value==style_label
                st.markdown(f'<div class="rh-style-card {"is-selected" if selected else ""}"><span class="rh-style-icon">{icon}</span>'
                            f'<small>{"2D / DATA" if value.startswith("2D") else "3D / MOTION"}</small><h3>{title}</h3><p>{description}</p></div>',unsafe_allow_html=True)
                st.button(('✓  ' if selected else '')+title,key='choose_'+value,on_click=_choose_style,args=(value,),width='stretch',type='primary' if selected else 'secondary')
    style="3D" if style_label.startswith("3D") else "2D"
    night=style_label=='3D · Chase'
    section_title('Pick your weekend','Races appear in calendar order. Choose a season to explore its grid.')
    with st.container(border=True,key="video_selection"):
        year_col,event_col,session_col=st.columns([1,2,1])
        with year_col:
            year=st.selectbox("Season",list(range(date.today().year,2017,-1)),key="video_year")
        try:
            events=event_loader(int(year))
        except Exception:
            events=[]
        with event_col:
            if events:
                if st.session_state.get('video_event') not in events:st.session_state.pop('video_event',None)
                event=st.selectbox("Grand Prix",events,index=events.index(latest["event_name"]) if latest["event_name"] in events else 0,format_func=event_label,key="video_event")
            else:
                event=st.text_input("Grand Prix",value=latest["event_name"],key="video_event_text")
        with session_col:
            session_label=st.selectbox("Session",["Qualifying","Race","Sprint","Sprint Qualifying"],key="video_session")
        session={"Qualifying":"Q","Race":"R","Sprint":"S","Sprint Qualifying":"SQ"}[session_label]
        selection_key=(int(year),event,session)
        st.markdown(track_card(event,year,session_label,race_lighting(year,event)),unsafe_allow_html=True)
        if st.button("Find the drivers  →",key="video_load_session",type='primary'):
            try:
                with st.spinner("Loading drivers, laps and telemetry…"):
                    loaded=catalog(*selection_key)
                st.session_state["video_catalog"]=loaded
                st.session_state["video_catalog_key"]=selection_key
            except Exception as exc:
                st.error(f"This session could not be loaded: {exc}")

    environment='Telemetry-built'
    ready,reason=availability(int(year),event,environment=environment) if style=="3D" else (True,"")
    if style=="3D" and not ready: st.info(reason)

    loaded=st.session_state.get("video_catalog")
    if not loaded or st.session_state.get("video_catalog_key")!=selection_key:
        # Keep cancellation available if session controls change during a render.
        _job_panel()
        st.markdown('<div class="rh-grid-wait"><span>THE GRID IS WAITING</span><h3>Who’s going head to head?</h3>'
                    '<p>Choose your weekend above to reveal the drivers and their laps.</p><div class="rh-empty-pair"><b>?</b><i>VS</i><b>?</b></div></div>',unsafe_allow_html=True)
        return
    entries=loaded["drivers"]
    codes=list(entries)
    # Reset only invalid previous choices when a session changes.
    for key in ("video_driver_a","video_driver_b"):
        if st.session_state.get(key) not in codes: st.session_state.pop(key,None)
    section_title('Choose your matchup','Two laps. One starting point. Who finds the edge?')
    with st.container(border=True,key="video_drivers"):
        first,second=st.columns(2,gap="large")
        with first:
            driver_a=st.selectbox("Driver A",codes,format_func=lambda code:f"{code} · {entries[code]['name']}",key="video_driver_a")
            st.markdown(driver_card(driver_a,entries[driver_a],'THE CHALLENGER'),unsafe_allow_html=True)
        with second:
            driver_b=st.selectbox("Driver B",codes,index=min(1,len(codes)-1),
                                 format_func=lambda code:f"{code} · {entries[code]['name']}",key="video_driver_b")
            st.markdown(driver_card(driver_b,entries[driver_b],'THE RIVAL'),unsafe_allow_html=True)
        mode_col,part_col=st.columns(2)
        with mode_col:
            mode=st.radio("Which laps?",["Fastest valid laps","Choose lap numbers"],horizontal=True,key="video_lap_mode")
        with part_col:
            part=st.selectbox("Qualifying segment",["All","Q1","Q2","Q3"],key="video_quali_part") if session in {"Q","SQ"} else "All"
        lap_a=lap_b=None
        if mode=="Choose lap numbers":
            choices_a=entries[driver_a].get("segments",{}).get(part,entries[driver_a]["laps"])
            choices_b=entries[driver_b].get("segments",{}).get(part,entries[driver_b]["laps"])
            if not choices_a or not choices_b:
                st.info("One of these drivers has no timed laps in this qualifying segment. Choose another segment or driver.")
                return
            ca,cb=st.columns(2)
            with ca: lap_a=st.selectbox(f"{driver_a} lap",choices_a,key=f"video_lap_a_{driver_a}_{year}_{session}_{event}_{part}")
            with cb: lap_b=st.selectbox(f"{driver_b} lap",choices_b,key=f"video_lap_b_{driver_b}_{year}_{session}_{event}_{part}")
        st.caption("Both laps start together. Each keeps its original duration. Ghosts share one display route and may overlap." if night else
                   "Both laps start together. Each keeps its original duration. These are ghost laps, with display paths separated for readability.")
    selection=VideoSelection(int(year),event,session,driver_a,driver_b,lap_a,lap_b,part)
    section_title('Make it yours','Choose the frame, camera and length. Your RH branding is included.')
    format_col,camera_col=st.columns(2)
    with format_col:
        orientation=st.radio("Frame",["Vertical · 9:16","Landscape · 16:9"],horizontal=True,key="video_orientation")
    with camera_col:
        if night:
            focus=st.radio('Follow',[0,1],horizontal=True,
                format_func=lambda value:(driver_a,driver_b)[value],key='video_night_focus_v2')
            camera=('Night chase A','Night chase B')[focus]
        else:camera=st.radio("Camera",["Follow cars","Full circuit"],horizontal=True,key="video_camera")
    start=0.; end=None;quality='Fast';preview_short=540
    if style=="3D":
        qc,rc=st.columns(2)
        with qc:quality=st.select_slider('Finish',['Fast','Balanced','High'],key='video_render_quality')
        with rc:preview_resolution=st.selectbox('Preview detail',['540p · Quick draft','720p · Clear preview','1080p · Full detail'],index=1,key='video_preview_resolution')
        preview_short=int(preview_resolution.split('p')[0])
        st.caption('Higher detail takes longer. Try a short clip before rendering a full lap.')
        range_col,start_col,duration_col=st.columns([1.3,1,1])
        with range_col:
            range_mode=st.radio("Length",["Short clip","Full lap"],horizontal=True,key="video_3d_range")
        if range_mode=="Short clip":
            with start_col: start=float(st.number_input("Start · lap seconds",min_value=0.,max_value=600.,value=0.,step=1.,key="video_3d_start"))
            with duration_col: duration=float(st.number_input("Clip duration · seconds",min_value=2.,max_value=30.,value=10.,step=1.,key="video_3d_duration"))
            end=start+duration
        else:
            st.caption("Full-lap 3D renders take longer, especially at 1080p. A short preview is a good first check.")
        with st.expander('About the visuals'):
            st.caption('Real lap timing and inputs, shown on an illustrative telemetry-built track. Cars share a display route; this does not reproduce each driver’s exact racing line. Lighting follows the venue’s usual race setting.')
    audio=st.selectbox('Soundtrack',['The Duel','Grit & Drums','Silent'],format_func=lambda v:'Industrial Cut' if v=='The Duel' else v,key='video_soundtrack')
    audio_volume=st.slider('Audio volume',0,100,80,5,key='video_audio_volume') if audio!='Silent' else 80
    st.caption('Audio is included in every preview and downloaded MP4 unless Silent is selected.')
    # Primitive values survive Streamlit module reloads; dataclass identity does not.
    signature=(selection.year,selection.event,selection.session,selection.driver_a,selection.driver_b,
               selection.lap_a,selection.lap_b,selection.qualifying_part,orientation,camera,style,start,end,
               RENDER_VERSION if style=='3D' else '2d', BRANDING_VERSION,environment,quality,preview_short,audio,audio_volume)
    current=video_jobs().snapshot(st.session_state.get("video_job_id"))
    busy=bool(current and current["status"] in {"queued","building","rendering"})
    if st.button("Create my preview  →",type="primary",key="video_build_preview",
                 disabled=busy or driver_a==driver_b or not ready):
        try:
            size=(preview_short,preview_short*16//9) if orientation.startswith("Vertical") else (preview_short*16//9,preview_short)
            st.session_state["video_job_id"]=video_jobs().submit(selection,size=size,fps=24,camera=camera,
                                                               style=style,start=start,end=end,environment=environment,quality=quality,audio=audio,audio_volume=audio_volume)
            st.session_state["video_job_signature"]=signature
            st.session_state.pop("video_result",None)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    if driver_a==driver_b: st.info("Choose two different drivers.")
    _job_panel()
    result=st.session_state.get("video_result")
    if not result:
        st.caption(f"Preview: {preview_short}p / 24 fps. Export: up to 1080p / " + ("30 fps." if style=="3D" else "60 fps.") + (' MP4 with instrumental audio and visible music credit.' if audio!='Silent' else ' Silent MP4.'))
        return
    if st.session_state.get("video_job_signature")!=signature:
        st.info("The controls have changed. Build a new preview to apply this selection.")
        return
    comparison=result["comparison"]
    if style=="3D":
        actual_end=min(comparison.duration,end) if end is not None else comparison.duration
        st.caption(f"3D · {start:.2f}–{actual_end:.2f}s of the selected laps · {camera}")
    content,settings=st.columns([2,1],gap="large")
    with content:
        with st.container(key="video_player_3d_portrait" if style=="3D" and orientation.startswith("Vertical") else "video_player"):
            st.video(str(result["result"]))
    with settings:
        section_title("The matchup")
        for lap in comparison.laps:
            st.markdown(f'<div class="rh-video-lap"><strong>{html.escape(lap.code)}</strong>'
                        f'<b>{lap_clock(lap.lap_time)}</b><span>Lap {lap.number} · {html.escape(lap.name)}</span></div>',unsafe_allow_html=True)
        a,b=comparison.laps
        st.caption(f"{a.code if a.lap_time<=b.lap_time else b.code} faster by {abs(a.lap_time-b.lap_time):.3f}s")
        resolution=st.selectbox("Export resolution",["720p","1080p"],key="video_resolution")
        fps=st.selectbox("Frame rate",[24,30] if style=="3D" else [30,60],format_func=lambda value:f"{value} fps",
                         key="video_3d_fps" if style=="3D" else "video_fps")
        st.caption("Exports run in the background. Keep this app running until the file is ready.")
        if st.button("Render final clip",key="video_export",disabled=busy):
            try:
                short=720 if resolution=="720p" else 1080
                size=(short,short*16//9) if orientation.startswith("Vertical") else (short*16//9,short)
                st.session_state["video_job_id"]=video_jobs().submit(selection,comparison=comparison,size=size,fps=fps,camera=camera,
                                                                   preview=False,style=style,start=start,end=end,environment=environment,quality=quality,audio=audio,audio_volume=audio_volume)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        path=result["result"]
        st.download_button("Download current MP4",data=path.read_bytes(),file_name=path.name,mime="video/mp4",key="video_download")
    if style=="3D":
        with st.expander("3D assets & accuracy"):
            st.caption('Circuit geometry is built from this session’s telemetry reference. Usable telemetry Z supplies estimated relative elevation; unreliable heights stay flat. Width, kerbs and scenery remain illustrative, not surveyed geometry.')
            st.markdown(f'Generic concept car by [Qvist_designs]({CAR_SOURCE}), '
                        '[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). '
                        'Modified scale/orientation, mesh detail and team-inspired materials. '
                        'Not an authentic team/year replica. Colors follow the selected session’s team metadata.')
            st.caption("Chase uses illustrative scenery, a close rear camera and overlapping ghosts on one display route. Lighting follows the venue’s usual race setting." if night else
                       "Stylized scenery, asphalt-constrained display route and adaptive ghost spacing. Lap clocks and telemetry stay unchanged. Rendered videos only; source models stay private.")
    if comparison.warnings:
        with st.expander("Lap data notes"):
            for warning in comparison.warnings: st.caption(warning)

"""Telemetry timing, loudness mastering and published-instrumental audio mux.

Production uses services.recorded_music's attributed recordings, not the old
procedural synth backing. The latter helper is retained for legacy diagnostics.
The audio mux copies the already-composed video stream.
"""
import json
import math
from pathlib import Path
import subprocess
import tempfile
import time
import wave
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import butter, sosfilt
from services.cinematic_timeline import cinematic_timeline
from services.limit_story import LimitStory, limit_timeline

VERSION='duel-2-cinematic-pulse'
SAMPLE_RATE=48000


def validate_audio(style='Silent',volume=80):
    if style not in ('Silent','The Duel','Grit & Drums'):
        raise ValueError('Choose Industrial Cut, Grit & Drums or Silent audio.')
    try:value=float(volume)
    except (TypeError,ValueError):raise ValueError('Audio volume must be between 0 and 100.') from None
    if isinstance(volume,bool) or not math.isfinite(value) or not 0<=value<=100:
        raise ValueError('Audio volume must be between 0 and 100.')
    return style,value


def soundtrack_timeline(comparison,*,fps,start=0,end=None,playback_speed=3,pacing='Constant',target_duration=35,camera='The Limit',style='3D'):
    if style=='2D':
        from services.video_timeline import frame_count,validate_playback_speed
        speed=validate_playback_speed(playback_speed)
        first=max(0,float(start));last=comparison.duration if end is None else min(comparison.duration,float(end))
        if last<=first:raise ValueError('The video range must contain some of the lap.')
        # Match render_mp4 exactly: the 2D renderer holds even short clips.
        count=frame_count(first,last,fps,speed,hold=True)
        return dict(source_times=np.minimum(last,first+np.arange(count)*speed/fps).tolist(),
                    fps=fps,action_seconds=(last-first)/speed,output_seconds=count/fps),last==comparison.duration
    if style!='3D':raise ValueError('Choose 2D or 3D rendering.')
    from services.video_3d import render_range
    start,end,_,full=render_range(comparison,start,end,fps,playback_speed)
    result=cinematic_timeline(comparison,start,end,fps,playback_speed,pacing,target_duration,full)
    if camera=='The Limit':result=limit_timeline(result)
    return result,full


def duel_controls(comparison,timeline,full):
    """All cue positions come from the existing exported source clock."""
    source=np.asarray(timeline['source_times'],float);fps=timeline['fps']
    if source.ndim!=1 or not len(source) or not np.isfinite(source).all() or (np.diff(source)<0).any():
        raise ValueError('Audio requires a finite, monotone source clock.')
    output=np.arange(len(source))/fps
    a,b=comparison.laps
    progress=np.minimum(a.progress_at(source),b.progress_at(source))
    delta=np.interp(progress,b._distance_progress,b._distance_times)-np.interp(progress,a._distance_progress,a._distance_times)
    if not np.isfinite(delta).all():raise ValueError('Audio requires finite matched-distance timing.')
    # Positive gap means A leads, matching the graphics. Keep both voices
    # audible; no binary leader switch or left/right-only encoding.
    dominance=gaussian_filter1d(np.tanh(delta/.12),max(1,fps*.10),mode='nearest')
    story=LimitStory(comparison,dict(progress=comparison.track[:,0],xy=comparison.track[:,1:3]))
    cues=[]
    for beat in story.beats:
        source_cue=a.time_at_distance(beat['start'])
        if source[0]<=source_cue<source[-1]:
            cues.append(dict(time=float(np.interp(source_cue,source,output)),driver=beat['driver'],gain=beat['gain']))
    finish=float(timeline.get('limit_intro_seconds',0)+timeline['action_seconds']) if full else None
    return dict(times=output,dominance=dominance,cues=cues,finish=finish,
                intro=float(timeline.get('limit_intro_seconds',0)),seconds=len(source)/fps)


def synthesize_duel(comparison,timeline,destination,*,full=True,cancelled=None):
    """Legacy diagnostic synth; not used by production video exports."""
    controls=duel_controls(comparison,timeline,full)
    rate=SAMPLE_RATE;total=round(controls['seconds']*rate)
    rng=np.random.default_rng(20261028)
    sos=butter(2,[650,4200],btype='bandpass',fs=rate,output='sos');filter_state=np.zeros((len(sos),2))
    period=60/128
    # Do not leave the first three seconds as only a thin rising noise.
    # Music establishes immediately; the analytical intro gets its own lift.
    attack=.08
    with wave.open(str(destination),'wb') as writer:
        writer.setnchannels(2);writer.setsampwidth(2);writer.setframerate(rate)
        for offset in range(0,total,rate):
            if cancelled and cancelled():raise InterruptedError('Audio generation cancelled.')
            t=(offset+np.arange(min(rate,total-offset)))/rate
            noise,filter_state=sosfilt(sos,rng.normal(0,1,len(t)),zi=filter_state)
            weight=np.interp(t,controls['times'],controls['dominance'])
            local=np.maximum(0,t-attack);beat=np.floor(local/period).astype(int)
            u=np.mod(local,period);env=np.sin(np.pi*u/period)**2*np.exp(-u*2.5)
            fa=np.array([110.,130.8128,164.8138,130.8128])[beat%4]
            fb=np.array([164.8138,195.9977,246.9417,220.])[beat%4]
            phase_a=2*np.pi*fa*u;phase_b=2*np.pi*fb*u
            warm=(np.sin(phase_a)-np.sin(3*phase_a)/9+np.sin(5*phase_a)/25)*env
            metal=(np.sin(phase_b)+.16*np.sin(2.003*phase_b))*env
            ga=.045*(.75+.30*weight);gb=.045*(.75-.30*weight)
            active=np.clip((t-attack)/.18,0,1)
            # Very small pan for space; the identity and advantage survive mono.
            left=active*(warm*ga+metal*gb*.87)
            right=active*(warm*ga*.87+metal*gb)
            drum_time=np.mod(local,period)
            kick=np.sin(2*np.pi*(46*drum_time+1.45*(1-np.exp(-drum_time/.033))))*np.exp(-drum_time*20)*.26
            snare_time=np.mod(local+period,period*2)
            snare=noise*np.exp(-snare_time*26)*.065
            hats=noise*np.exp(-np.mod(local,period/2)*90)*.018
            # A speaker-readable bass ostinato replaces the exposed high
            # arpeggio. Harmonics remain well below Nyquist; no engine mimicry.
            eighth=period/2;bu=np.mod(local,eighth)
            bass_notes=np.array([55.,55.,82.4069,55.,65.4064,55.,73.4162,82.4069])
            bass_frequency=bass_notes[np.floor(local/eighth).astype(int)%8]
            bass_phase=2*np.pi*bass_frequency*bu
            bass_env=np.minimum(1,bu/.008)*np.exp(-bu*13)
            bass=np.tanh(1.8*(np.sin(bass_phase)+.42*np.sin(2*bass_phase)+.18*np.sin(3*bass_phase)))*bass_env*.13
            # Smooth minor harmony fills the midrange without a ringtone lead.
            breath=.7+.3*np.sin(np.pi*np.minimum(u/.20,1))**2
            bed=(np.sin(2*np.pi*110*t)+.42*np.sin(2*np.pi*130.8128*t)+.34*np.sin(2*np.pi*164.8138*t))*breath*.025
            chapter=.74+.22*np.sin(np.pi*np.clip(local/max(1,controls['seconds']-2),0,1))**2
            if controls['intro']:
                chapter*=.72+.28*np.clip((t-controls['intro']+.25)/.25,0,1)
            common=active*(kick+snare+hats+bass+bed)*chapter
            # Immediate rounded cinematic hit, followed by a short rising air
            # texture while the canyon grows. No full-volume broadband blast.
            hit=np.sin(2*np.pi*(47*t+1.8*(1-np.exp(-t/.025))))*np.exp(-t*9)*.36
            hit+=noise*np.exp(-t*28)*.07
            rise_end=max(.55,controls['intro'])
            rise=np.clip(t/rise_end,0,1)**2*np.clip((rise_end-t)/.18,0,1)*noise*.026
            common+=hit+rise
            duck=np.ones(len(t))
            accents=np.zeros(len(t))
            for cue in controls['cues']:
                dt=t-cue['time']
                duck*=1-.65*np.exp(-((dt+.09)/.10)**2)
                v=np.maximum(dt,0);gate=(dt>=0)&(dt<.55)
                pitch=164.8138 if cue['driver']==0 else 195.9977
                accent=(np.sin(2*np.pi*pitch*v)+.3*np.sin(2*np.pi*pitch*2*v))*np.exp(-v*14)*gate*.12
                accent+=noise*np.exp(-v*28)*gate*.035
                accents+=accent
            mix=(np.column_stack([left,right])+common[:,None])*duck[:,None]+accents[:,None]
            if controls['finish'] is not None:
                finish=controls['finish'];quiet=1-.99*np.exp(-((t-finish)/.095)**4)
                fade=np.clip((finish+.20-t)/.3,0,1)
                mix*=(quiet*fade)[:,None]
                # RACE HYPE signature: three ascending original notes plus a
                # warm final chord, aligned to the actual result hold.
                for delay,freq in ((.14,220.),(.33,329.6276),(.52,440.)):
                    dt=t-finish-delay;v=np.maximum(0,dt)
                    note=(np.sin(2*np.pi*freq*v)+.16*np.sin(2*np.pi*freq*2*v))*np.exp(-v*4.5)*np.minimum(1,v/.012)*(dt>=0)*.14
                    mix+=note[:,None]
            ending=np.clip((controls['seconds']-t)/.08,0,1)
            mix=np.tanh(mix*1.5)*ending[:,None]
            writer.writeframes((np.clip(mix,-1,1)*32767).astype('<i2').tobytes())
    return dict(version=VERSION,seconds=controls['seconds'],frames=total,sample_rate=rate,
                cues=controls['cues'],finish=controls['finish'],meaning='Original musical sonification, not recorded engine audio')


def _run(command,cancelled=None):
    flags=dict(creationflags=subprocess.CREATE_NO_WINDOW) if hasattr(subprocess,'CREATE_NO_WINDOW') else {}
    with tempfile.TemporaryFile() as log:
        process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=log,**flags)
        try:
            while process.poll() is None:
                if cancelled and cancelled():raise InterruptedError('Audio export cancelled.')
                time.sleep(.08)
            log.seek(0);message=log.read().decode(errors='replace')
            if process.returncode:raise RuntimeError('Audio encoding failed: '+message[-1800:])
            return message
        finally:
            if process.poll() is None:process.kill();process.wait()


def attach_duel(comparison,source,destination,timeline,*,full=True,volume=80,cancelled=None,soundtrack='The Duel'):
    """Loudness-controlled AAC, atomic publish, original video packets copied."""
    _,volume=validate_audio(soundtrack,volume)
    from services.recorded_music import render_recorded_score
    source=Path(source);destination=Path(destination)
    pending=destination.with_suffix('.audio.partial.mp4')
    try:
        with tempfile.TemporaryDirectory(prefix='rh_duel_') as folder:
            wav=Path(folder)/'duel.wav'
            report=render_recorded_score(comparison,timeline,wav,full=full,style=soundtrack,cancelled=cancelled)
            stats=_run(['ffmpeg','-hide_banner','-nostdin','-i',str(wav),'-af','loudnorm=I=-16:TP=-2:LRA=8:print_format=json','-f','null','-'],cancelled)
            measured=json.loads(stats[stats.rfind('{'):stats.rfind('}')+1])
            if not all(math.isfinite(float(measured[k])) for k in ('input_i','input_tp','input_lra','input_thresh','target_offset')):
                raise RuntimeError('Soundtrack loudness analysis was not finite.')
            normalization=('loudnorm=I=-16:TP=-2:LRA=8:linear=true:measured_I='+measured['input_i']+
                ':measured_TP='+measured['input_tp']+':measured_LRA='+measured['input_lra']+
                ':measured_thresh='+measured['input_thresh']+':offset='+measured['target_offset'])
            _run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-y','-i',str(source),'-i',str(wav),
                  '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000',
                  '-af',normalization+f',volume={volume/100:.6f}',
                  '-t',f'{report["seconds"]:.9f}','-movflags','+faststart',
                  '-metadata','comment='+report['music']['attribution'],str(pending)],cancelled)
            if cancelled and cancelled():raise InterruptedError('Audio export cancelled.')
            pending.replace(destination)
            report.update(volume=volume,loudness_target_lufs=-16,true_peak_target_db=-2,video_stream_copy=True)
            return report
    finally:pending.unlink(missing_ok=True)

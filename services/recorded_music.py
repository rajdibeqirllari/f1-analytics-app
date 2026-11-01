"""Published instrumental recordings, explicit attribution and adaptive edits.

These are full mixes, NOT isolated drum/bass stems. No invented source
separation and no synthetic backing-track fallback when an asset is missing.
"""
from functools import lru_cache
import hashlib
from pathlib import Path
import subprocess
import wave
import numpy as np
from PIL import ImageDraw

ROOT=Path(__file__).resolve().parents[1]
VERSION='recorded-industrial-1'
MIX_VERSION='continuous-music-2'
LICENSE='https://creativecommons.org/licenses/by/4.0/'
TRACKS={
    'The Duel':dict(label='Industrial Cut',title='Industrial Cinematic',author='Kevin MacLeod',
        filename='industrial-cinematic.mp3',bpm=110,isrc='USUAN1600047'),
    'Grit & Drums':dict(label='Grit & Drums',title='Gearhead',author='Kevin MacLeod',
        filename='gearhead.mp3',bpm=68,isrc='USUAN1100221'),
}


def music_info(style='The Duel'):
    if style=='Silent':return None
    if style not in TRACKS:raise ValueError('Choose Industrial Cut, Grit & Drums or Silent.')
    track=TRACKS[style]
    source='https://incompetech.com/music/royalty-free/index.html?isrc='+track['isrc']
    return dict(title=track['title'],author=track['author'],source=source,license=LICENSE,
                attribution=f'"{track["title"]}" by {track["author"]} (incompetech.com). CC BY 4.0: {LICENSE} Source: {source} Edited: excerpts, looping, fades and telemetry-driven ducking. Additional short accents: RACE HYPE.',
                version=VERSION)


@lru_cache(maxsize=2)
def _decode(path,revision):
    flags=dict(creationflags=subprocess.CREATE_NO_WINDOW) if hasattr(subprocess,'CREATE_NO_WINDOW') else {}
    pcm=subprocess.check_output(['ffmpeg','-v','error','-nostdin','-i',str(path),'-t','600',
        '-vn','-ar','48000','-ac','2','-f','s16le','pipe:1'],**flags)
    samples=np.frombuffer(pcm,'<i2').reshape(-1,2).astype(np.float32)/32768
    if len(samples)<48000*8 or not np.isfinite(samples).all():
        raise ValueError('Published music asset is empty, too short or invalid.')
    samples.setflags(write=False)
    return samples


def load_track(style='The Duel'):
    if style not in TRACKS:raise ValueError('Unsupported recorded soundtrack.')
    path=ROOT/'assets'/'music'/TRACKS[style]['filename']
    if not path.is_file():
        raise ValueError('Published soundtrack is missing: '+path.name+'. Restore assets/music; no synth fallback was used.')
    return _decode(str(path),path.stat().st_mtime_ns)


def strong_entry(samples,rate=48000):
    """Select an energetic onset, skipping a quiet intro; no claimed bar map."""
    count=min(len(samples)//4800,600)
    if count<40:return 0.
    mono=samples[:count*4800].mean(1).reshape(count,4800)
    energy=np.sqrt(np.mean(mono*mono,axis=1))
    smooth=np.convolve(energy,np.ones(20)/20,mode='same')
    threshold=np.percentile(smooth[10:-10],70)*.85
    candidates=np.flatnonzero((smooth>=threshold)&(np.arange(count)>=10)&(np.arange(count)<count-20))
    if not len(candidates):return 0.
    beginning=int(candidates[0]);window=energy[beginning:beginning+20]
    onset=beginning+int(np.argmax(np.diff(window,prepend=0)))
    return onset*.1


def recorded_block(samples,t,entry,rate=48000):
    """Continuous full recording; crossfade only when long exports need a loop."""
    duration=len(samples)/rate;crossfade=.25
    length=duration-entry-crossfade
    if length<=1:raise ValueError('Soundtrack entry is too close to the end.')
    phase=np.mod(t,length)
    position=phase+entry+crossfade
    index=np.minimum((position*rate).astype(np.int64),len(samples)-1)
    output=samples[index].copy()
    fraction=np.clip((phase-(length-crossfade))/crossfade,0,1)
    if fraction.any():
        # End region overlaps the beginning of the next traversal. The next
        # cycle begins after this overlapped .25s, not before it.
        next_index=np.minimum(((entry+fraction*crossfade)*rate).astype(np.int64),len(samples)-1)
        angle=fraction*np.pi/2
        output=output*np.cos(angle)[:,None]+samples[next_index]*np.sin(angle)[:,None]
    return output


def render_recorded_score(comparison,timeline,destination,*,full=True,style='The Duel',cancelled=None):
    from services.duel_audio import duel_controls
    controls=duel_controls(comparison,timeline,full)
    samples=load_track(style);entry=strong_entry(samples);rate=48000
    total=round(controls['seconds']*rate);rng=np.random.default_rng(613)
    # Scale conservatively before the existing two-pass loudness stage.
    peak=max(.05,float(np.percentile(np.abs(samples[::8]),99.5)))
    gain=.42/peak
    # Short acoustic-like accent drawn from the recording's own strong onset;
    # its full-mix character is preserved, not represented as a separate stem.
    hit=samples[int(entry*rate):int(entry*rate)+round(.28*rate)]
    with wave.open(str(destination),'wb') as writer:
        writer.setnchannels(2);writer.setsampwidth(2);writer.setframerate(rate)
        for offset in range(0,total,rate):
            if cancelled and cancelled():raise InterruptedError('Audio generation cancelled.')
            t=(offset+np.arange(min(rate,total-offset)))/rate
            music=recorded_block(samples,t,entry)*gain
            # Subtle tension ride; tempo and pitch of the recording stay fixed.
            dominance=np.interp(t,controls['times'],controls['dominance'])
            energy=.83+.12*(1-np.abs(dominance))
            accents=np.zeros((len(t),2))
            for cue in controls['cues']:
                dt=t-cue['time']
                v=np.maximum(dt,0);idx=np.minimum((v*rate).astype(int),len(hit)-1)
                envelope=(dt>=0)*(dt<.24)*np.minimum(1,v/.004)*np.exp(-v*15)
                accents+=hit[idx]*envelope[:,None]*gain*.18
                # Restrained ratchet-like texture: filtered noise clicks, not
                # a fabricated recording of a real pit tool or engine.
                teeth=np.exp(-np.mod(v,.026)*190)*(dt>=0)*(dt<.13)*np.exp(-v*22)
                clicks=rng.normal(0,1,len(t))*teeth*.013
                accents+=clicks[:,None]
            envelope=np.minimum(1,t/.018)
            # Graphics never gate the backing music. Keep it running through
            # gain callouts, the result card AND the final sculpture. Only the
            # actual end of the exported file receives a short fade.
            ending=np.clip((controls['seconds']-t)/.18,0,1)
            mixed=(music*(energy*envelope)[:,None]+accents)*ending[:,None]
            # Very soft safety saturation only; final master normalizes peaks.
            mixed=np.tanh(mixed*.9)
            writer.writeframes((mixed*32767).astype('<i2').tobytes())
    return dict(version=MIX_VERSION,seconds=controls['seconds'],frames=total,sample_rate=rate,
                cues=controls['cues'],finish=controls['finish'],source_entry_seconds=entry,
                cue_ducking=False,music_continues_through_results=True,end_fade_seconds=.18,
                music=music_info(style),meaning='Published instrumental full mix with adaptive edits; no vocals or fake engine audio')


def add_music_credit(image,credit):
    if not credit:return image
    from services.video_3d_overlay import font
    image=image.convert('RGB');d=ImageDraw.Draw(image);w,h=image.size
    scale=w/(540 if h>w else 960);height=max(20,round(27*scale))
    d.rectangle((0,h-height,w,h),fill='#07101a')
    lines=[f'Music: {credit["title"]} — {credit["author"]} · incompetech.com',
           'CC BY 4.0 · creativecommons.org/licenses/by/4.0/ · edited']
    size=max(6,round(7.5*scale))
    for i,line in enumerate(lines):
        # Keep legal attribution in frame at every supported aspect ratio.
        while size>5 and d.textlength(line,font=font(size))>w-16*scale:size-=1
        d.text((round(8*scale),h-height+round((3+i*11)*scale)),line,font=font(size),fill='#a9bac9')
    return image

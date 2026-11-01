"""Experimental local sample mixer, independent of the pack's Studio master bus.

Uses FMOD Core to decode unencrypted FSB samples. It does not reproduce the
author's Studio mix or claim to be actual onboard audio. Samples stay local.
Audio Engine supplied by FMOD by Firelight Technologies.
"""
import ctypes as C
import os
from pathlib import Path
import tempfile
import numpy as np
from services.fmod_audio import SDK

# Verified sample names from each supplied bank; no other team's substitute.
SAMPLE_PROFILES={'rbv2':{'on':'on','decel':'decel','wind':'wind'},
                 'ferrari v3':{'on':'on','decel':'decel3','wind':'wind'}}


def decode_samples(bank, names):
    """Decode named subsounds through the matching vendor SDK, not a bank patch."""
    bank=Path(bank)
    lib=C.WinDLL(str(SDK/'lowlevel/lib/fmod64.dll'))
    def call(name,*args):
        result=getattr(lib,'FMOD_'+name)(*args)
        if result:raise RuntimeError(f'FMOD sample decode {name}: {result}')
    system=C.c_void_p();call('System_Create',C.byref(system))
    try:
        call('System_SetOutput',system,4)
        call('System_Init',system,32,0,None)
        with tempfile.TemporaryDirectory(dir=bank.parent) as folder:
            data=bank.read_bytes();offset=data.find(b'FSB5')
            if offset<0:raise ValueError('No unencrypted sample container found.')
            fsb=Path(folder)/'samples.fsb';fsb.write_bytes(data[offset:]);del data
            sound=C.c_void_p()
            call('System_CreateSound',system,os.fsencode(fsb),0x2081,None,C.byref(sound))
            count=C.c_int();call('Sound_GetNumSubSounds',sound,C.byref(count))
            result={}
            for i in range(count.value):
                sub=C.c_void_p();call('Sound_GetSubSound',sound,i,C.byref(sub))
                name=C.create_string_buffer(512);call('Sound_GetName',sub,name,512)
                name=name.value.decode(errors='replace')
                if name not in names:continue
                typ,fmt,channels,bits=(C.c_int() for _ in range(4))
                call('Sound_GetFormat',sub,C.byref(typ),C.byref(fmt),C.byref(channels),C.byref(bits))
                frequency=C.c_float();priority=C.c_int()
                call('Sound_GetDefaults',sub,C.byref(frequency),C.byref(priority))
                # PCM16 / PCM32 / float are the decoded output formats supported here.
                dtype={2:np.dtype('<i2'),4:np.dtype('<i4'),5:np.dtype('<f4')}.get(fmt.value)
                if dtype is None:raise ValueError(f'Unsupported decoded sample format {fmt.value}.')
                length=C.c_uint();call('Sound_GetLength',sub,C.byref(length),4)
                remaining=length.value
                if remaining>100_000_000:raise ValueError('Sample exceeds the decoding safety limit.')
                chunks=[];buffer=C.create_string_buffer(262144)
                while remaining:
                    read=C.c_uint()
                    status=lib.FMOD_Sound_ReadData(sub,buffer,min(len(buffer),remaining),C.byref(read))
                    if read.value:
                        chunks.append(buffer.raw[:read.value]);remaining-=read.value
                    if status or not read.value:
                        if status not in (0,16):raise RuntimeError(f'FMOD sample read failed ({status}).')
                        break
                pcm=np.frombuffer(b''.join(chunks),dtype=dtype).astype(np.float32)
                if dtype.kind=='i':pcm/=float(2**(bits.value-1))
                pcm=pcm.reshape(-1,channels.value).mean(axis=1)
                result[name]=(pcm,int(round(frequency.value)))
            call('Sound_Release',sound)
            return result
    finally:
        call('System_Release',system)


def steady_grain(audio, rate, duration=.32):
    """Choose a loud, locally stable sustained fragment; exclude initial transients."""
    width=int(rate*duration)
    if len(audio)<width*2:raise ValueError('Engine sample is too short.')
    candidates=[]
    for start in range(width,len(audio)-width,max(1,width//2)):
        segment=audio[start:start+width]
        energies=np.array([np.mean(p*p) for p in np.array_split(segment,8)])
        level=float(np.mean(energies))
        if level>1e-5:
            candidates.append((float(np.std(energies)/(level+1e-8)),start,level))
    if not candidates:raise ValueError('No audible sustained engine fragment found.')
    loudest=max(p[2] for p in candidates)
    _,start,_=min(p for p in candidates if p[2]>=loudest*.25)
    grain=audio[start:start+width].copy()
    # Join with an equal-power overlap instead of repeating an abrupt waveform seam.
    fade=int(rate*.035);a=np.linspace(0,np.pi/2,fade)
    join=grain[-fade:]*np.cos(a)+grain[:fade]*np.sin(a)
    loop=np.r_[grain[fade:-fade],join].astype(np.float32)
    loop*=min(8.,.18/max(1e-6,float(np.sqrt(np.mean(loop*loop)))))
    return loop


def measured_pitch(audio, rate):
    """Dominant low engine band, not guaranteed firing fundamental or source RPM."""
    from scipy.signal import periodogram
    f,p=periodogram(audio,rate,window='hann',nfft=max(8192,2**int(np.ceil(np.log2(len(audio))))))
    indices=np.flatnonzero((f>=220)&(f<=750))
    peak=indices[np.argmax(p[indices])]
    # Parabolic sub-bin estimate for a narrow peak.
    y=np.log(np.maximum(p[peak-1:peak+2],1e-20))
    correction=.5*(y[0]-y[2])/(y[0]-2*y[1]+y[2]+1e-20)
    return float(f[peak]+np.clip(correction,-.5,.5)*(f[1]-f[0]))


def calibrated_layers(audio, rate):
    """Select several long stable sections; retain their independently measured pitch."""
    width=min(int(rate*1.6),len(audio)//2)
    if width<int(rate*.5):raise ValueError('Engine recording is too short for sustained layers.')
    candidates=[]
    for start in range(0,len(audio)-width+1,max(1,int(rate*.4))):
        section=audio[start:start+width]
        powers=np.array([np.mean(x*x) for x in np.array_split(section,8)])
        level=float(np.mean(powers))
        if level<1e-5:continue
        pitches=np.array([measured_pitch(x,rate) for x in np.array_split(section,4)])
        variation=float(np.std(pitches)/np.mean(pitches))
        candidates.append(dict(start=start,pitch=float(np.median(pitches)),
                               score=variation+float(np.std(powers)/(level+1e-12))*.15,
                               level=level))
    if not candidates:raise ValueError('No audible engine sections found.')
    loudest=max(c['level'] for c in candidates)
    candidates=[c for c in candidates if c['level']>loudest*.15]
    selected=[]
    for target in (300.,400.,500.,600.):
        ranked=sorted(candidates,key=lambda c:c['score']+abs(np.log(c['pitch']/target))*.4)
        choice=next((c for c in ranked if all(abs(c['start']-s['start'])>=width//2 for s in selected)),ranked[0])
        if all(choice['start']!=s['start'] for s in selected):selected.append(choice)
    layers=[]
    for c in selected:
        grain=audio[c['start']:c['start']+width].copy()
        fade=int(rate*.08);a=np.linspace(0,np.pi/2,fade)
        join=grain[-fade:]*np.cos(a)+grain[:fade]*np.sin(a)
        grain=np.r_[grain[fade:-fade],join].astype(np.float32)
        grain*=min(6.,.16/max(1e-6,float(np.sqrt(np.mean(grain*grain)))))
        layers.append(dict(audio=grain,pitch=c['pitch'],source_start=c['start']/rate,
                           stability=c['score']))
    return sorted(layers,key=lambda c:c['pitch'])


def mix_layers(layers, target_pitch):
    """Continuous playback per source, with smoothly varying neighbouring-layer weights."""
    pitches=np.array([layer['pitch'] for layer in layers])
    # Soft selection avoids abrupt sample switches as RPM passes a layer boundary.
    distance=np.abs(np.log(np.maximum(target_pitch[:,None],1)/pitches))
    weights=np.exp(-((distance-distance.min(axis=1)[:,None])/.10)**2)
    weights/=np.maximum(np.sqrt(np.sum(weights*weights,axis=1))[:,None],1e-9)
    result=np.zeros(len(target_pitch))
    for i,layer in enumerate(layers):
        grain=layer['audio']
        ratio=np.clip(target_pitch/layer['pitch'],.4,2.1)
        phase=np.cumsum(ratio)%len(grain)
        index=phase.astype(np.int64);frac=phase-index
        result+=(grain[index]*(1-frac)+grain[(index+1)%len(grain)]*frac)*weights[:,i]
    return result


def synthesize(controls, samples, rate=48000):
    """Multi-section approximate engine reconstruction, not original FMOD event mixing.

Pitch is calibrated from audio's dominant engine band. Mapping that band to
RPM/20 assumes a V6 firing component; ambiguous source harmonics remain an
explicit approximation, not recovered original recording RPM metadata.
"""
    from scipy.signal import resample_poly
    from math import gcd
    def source(name):
        audio,sr=samples[name]
        d=gcd(sr,rate)
        return resample_poly(audio,rate//d,sr//d).astype(np.float32)
    on=calibrated_layers(source('on'),rate)
    off=calibrated_layers(source('decel'),rate)
    duration=float(controls['time'][-1]);n=int(round(duration*rate))
    t=np.arange(n)/rate
    rpm=np.interp(t,controls['time'],controls['rpms'])
    throttle=np.interp(t,controls['time'],controls['throttle'])
    speed=np.interp(t,controls['time'],controls['speed_kmh'])
    # Smooth pedal-driven layer changes over 25 ms without blurring RPM/shift timing.
    from scipy.ndimage import gaussian_filter1d
    load=np.clip(gaussian_filter1d(throttle,rate*.012,mode='nearest'),0,1)
    target=np.maximum(rpm,3000)/20.
    engine=mix_layers(on,target)*np.sqrt(load)*.80+mix_layers(off,target)*np.sqrt(1-load)*.60
    gain=np.ones(n)
    for shift in controls['shifts']:
        if shift['direction']=='up':
            a=max(0,int(shift['time']*rate));b=min(n,a+int(.045*rate))
            if b>a:gain[a:b]=1-.55*np.sin(np.linspace(0,np.pi,b-a))
    engine*=gain
    if 'wind' in samples:
        wind=source('wind');p=np.arange(n)%len(wind)
        engine+=wind[p]*np.clip(speed/330,0,1)**2*.14
    # Constant headroom adjustment for the entire clip, not hard clipping or
    # a time-varying limiter that could pump with every gear shift.
    audio=engine*.85
    peak=float(np.max(np.abs(audio))) if len(audio) else 0.
    audio*=min(1.,.95/max(peak,1e-9))
    fade=min(int(rate*.012),n//2)
    if fade:
        audio[:fade]*=np.linspace(0,1,fade);audio[-fade:]*=np.linspace(1,0,fade)
    return audio.astype(np.float32)


def render_sample_audio(spec, destination):
    from scipy.io import wavfile
    bank=Path(spec['bank'])
    profile=SAMPLE_PROFILES.get(bank.parent.name)
    if profile is None:raise ValueError('Sampled audio currently supports Red Bull and Ferrari only.')
    stamp=f'{bank.stat().st_size}-{bank.stat().st_mtime_ns}'
    cache=bank.parent/f'.decoded-engine-{stamp}.npz'
    if cache.is_file():
        with np.load(cache,allow_pickle=False) as data:
            samples={name:(data[name],int(data[name+'_rate'])) for name in ('on','decel','wind') if name in data}
    else:
        decoded=decode_samples(bank,set(profile.values()))
        samples={key:decoded[value] for key,value in profile.items() if value in decoded}
        if not {'on','decel'}<=samples.keys():
            raise ValueError('This team needs a verified sample profile; no guessed substitute was used.')
        values={}
        for name,(audio,rate) in samples.items():values.update({name:audio,name+'_rate':rate})
        np.savez(cache,**values)
    audio=synthesize(spec['controls'],samples)
    if not np.isfinite(audio).all():raise ValueError('Engine mix contains invalid samples; no WAV was published.')
    wavfile.write(destination,48000,(audio*32767).astype(np.int16))


if __name__=='__main__':
    import json
    import sys
    spec=json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
    render_sample_audio(spec,sys.argv[2])

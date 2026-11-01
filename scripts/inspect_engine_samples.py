"""Inspect unencrypted samples using the user's local FMOD Core SDK.

Does not edit banks, decrypt assets, or recreate their Studio mixer.
"""
import ctypes as C
import json
import os
import tempfile
from pathlib import Path
from services.engine_audio import bank_for_team
from services.fmod_audio import SDK


def inspect(team='Red Bull Racing'):
    bank=bank_for_team(team,2026)
    data=bank['bank'].read_bytes()
    offset=data.find(b'FSB5')
    if offset<0:raise ValueError('No unencrypted FSB sample container found.')
    lib=C.WinDLL(str(SDK/'lowlevel/lib/fmod64.dll'))
    def call(name,*args):
        result=getattr(lib,'FMOD_'+name)(*args)
        if result:raise RuntimeError(f'{name}: FMOD error {result}')
    system=C.c_void_p()
    call('System_Create',C.byref(system))
    try:
        call('System_SetOutput',system,4)  # NOSOUND_NRT
        call('System_Init',system,32,0,None)
        with tempfile.TemporaryDirectory(dir='tmp') as temp:
            fsb=Path(temp)/'samples.fsb'
            fsb.write_bytes(data[offset:])
            sound=C.c_void_p()
            call('System_CreateSound',system,os.fsencode(fsb.resolve()),0x2080,None,C.byref(sound))
            n=C.c_int();call('Sound_GetNumSubSounds',sound,C.byref(n))
            result=[]
            for i in range(n.value):
                sub=C.c_void_p();call('Sound_GetSubSound',sound,i,C.byref(sub))
                name=C.create_string_buffer(512);call('Sound_GetName',sub,name,512)
                length=C.c_uint();call('Sound_GetLength',sub,C.byref(length),1)
                result.append(dict(index=i,name=name.value.decode(errors='replace'),seconds=length.value/1000))
            call('Sound_Release',sound)
            return result
    finally:
        call('System_Release',system)


if __name__=='__main__':
    print(json.dumps(inspect(),indent=2))

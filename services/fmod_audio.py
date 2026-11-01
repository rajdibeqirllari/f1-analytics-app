"""Local FMOD 1.08.12 offline renderer. Never bundled with distributed builds.

Audio Engine supplied by FMOD by Firelight Technologies.
The user supplies and licenses the SDK and sound banks separately.
"""
import ctypes as C
import os
import uuid
from pathlib import Path

SDK = Path(__file__).resolve().parents[1]/'assets/sounds/fmod-api-1.08.12/api'


class Parameter(C.Structure):
    _fields_ = [('name', C.c_char_p), ('index', C.c_int), ('minimum', C.c_float),
                ('maximum', C.c_float), ('default', C.c_float), ('type', C.c_int)]


class Runtime:
    def __init__(self, output):
        debug = os.environ.get('RACEHYPE_FMOD_DEBUG') == '1'
        suffix = 'L64.dll' if debug else '64.dll'
        self.core = C.WinDLL(str(SDK/('lowlevel/lib/fmod'+suffix)))
        self.studio = C.WinDLL(str(SDK/('studio/lib/fmodstudio'+suffix)))
        if debug:
            self.call_core('Debug_Initialize', 7, 1, None, b'fmod-probe.log')
        self.system = C.c_void_p()
        self.call('System_Create', C.byref(self.system), C.c_uint(0x00010812))
        try:
            core = C.c_void_p()
            self.call('System_GetLowLevelSystem', self.system, C.byref(core))
            plugin = C.c_uint()
            self.call_core('System_LoadPlugin', core,
                           os.fsencode(SDK/'lowlevel/lib/fmod_distance_filter64.dll'),
                           C.byref(plugin), 0)
            self.call_core('System_SetOutput', core, 5)  # WAVWRITER_NRT, SDK enum
            self.call_core('System_SetSoftwareFormat', core, 48000, 3, 0)  # stereo
            self.call_core('System_SetDSPBufferSize', core, C.c_uint(480), 4)
            self.filename = C.create_string_buffer(os.fsencode(output))
            self.call('System_Initialize', self.system, 128, 4, 0, self.filename)
        except BaseException:
            self.close()
            raise

    def call(self, name, *args):
        result = getattr(self.studio, 'FMOD_Studio_'+name)(*args)
        if result:
            raise RuntimeError(f'FMOD {name} failed ({result}).')

    def call_core(self, name, *args):
        result = getattr(self.core, 'FMOD_'+name)(*args)
        if result:
            raise RuntimeError(f'FMOD {name} failed ({result}).')

    def load(self, bank):
        master = SDK.parent/'master.bank'
        if master.is_file():
            ptr = C.c_void_p()
            self.call('System_LoadBankFile', self.system, os.fsencode(master), 0, C.byref(ptr))
        ptr = C.c_void_p()
        self.call('System_LoadBankFile', self.system, os.fsencode(bank), 0, C.byref(ptr))
        self.call('Bank_LoadSampleData', ptr)
        self.call('System_FlushSampleLoading', self.system)

    def event(self, guid):
        ident = C.create_string_buffer(uuid.UUID(guid.strip('{}')).bytes_le)
        desc = C.c_void_p()
        self.call('System_GetEventByID', self.system, ident, C.byref(desc))
        count = C.c_int()
        self.call('EventDescription_GetParameterCount', desc, C.byref(count))
        parameters = {}
        for i in range(count.value):
            p = Parameter()
            self.call('EventDescription_GetParameterByIndex', desc, i, C.byref(p))
            parameters[p.name.decode()] = (p.minimum, p.maximum, p.default)
        instance = C.c_void_p()
        self.call('EventDescription_CreateInstance', desc, C.byref(instance))
        return instance, parameters

    def close(self):
        if self.system.value:
            self.call('System_Release', self.system)
            self.system = C.c_void_p()


def inspect_bank(team='Red Bull Racing'):
    import tempfile
    from services.engine_audio import bank_for_team
    bank = bank_for_team(team, 2026)
    with tempfile.TemporaryDirectory() as folder:
        rt = Runtime(str(Path(folder)/'probe.wav'))
        try:
            rt.load(bank['bank'])
            return {name: rt.event(bank['events'][name]['guid'])[1]
                    for name in ('engine_int', 'gear_int', 'wind')}
        finally:
            rt.close()


def render_controls(bank, events, controls, output):
    """Render one 10ms mixer block per telemetry step, independent of wall time."""
    import math
    rt = Runtime(str(Path(output).resolve()))
    try:
        rt.load(bank)
        engine, ep = rt.event(events['engine_int']['guid'])
        wind, wp = rt.event(events['wind']['guid'])
        if not {'rpms', 'throttle'} <= ep.keys() or 'speed' not in wp:
            raise ValueError('This bank does not expose the verified telemetry controls.')
        def setp(instance, name, value):
            rt.call('EventInstance_SetParameterValue', instance, name.encode(), C.c_float(value))
        rt.call('EventInstance_SetVolume', wind, C.c_float(.22))
        if 'air_pressure' in wp:
            setp(wind, 'air_pressure', 1.)
        shifts = iter(controls['shifts'])
        shift = next(shifts, None)
        n = math.ceil(controls['time'][-1]*100)
        for i in range(n):
            t = i/100
            setp(engine, 'rpms', min(ep['rpms'][1], max(ep['rpms'][0], controls['rpms'][i])))
            setp(engine, 'throttle', controls['throttle'][i])
            setp(wind, 'speed', min(wp['speed'][1], max(wp['speed'][0], controls['speed_kmh'][i])))
            if i == 0:
                rt.call('EventInstance_Start', engine)
                rt.call('EventInstance_Start', wind)
            while shift and shift['time'] <= t+1e-7:
                gear, gp = rt.event(events['gear_int']['guid'])
                if 'state' not in gp:
                    raise ValueError('This bank has no verified gear-shift state parameter.')
                setp(gear, 'state', 1. if shift['direction']=='up' else 0.)
                rt.call('EventInstance_Start', gear)
                rt.call('EventInstance_Release', gear)
                shift = next(shifts, None)
            rt.call('System_Update', rt.system)
    finally:
        rt.close()


if __name__ == '__main__':
    import json
    import sys
    if len(sys.argv) == 3:
        spec = json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
        render_controls(spec['bank'], spec['events'], spec['controls'], sys.argv[2])
    else:
        print(json.dumps(inspect_bank(), indent=2))

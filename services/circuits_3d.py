"""Explicit 3D circuit catalogue; downloaded assets and telemetry-built tracks."""
from dataclasses import dataclass
from datetime import date
from services.car_style import CAR_CREDIT


@dataclass(frozen=True)
class Circuit3D:
    key: str
    name: str
    event: str
    backend: str
    preset_year: int
    session: str = 'Qualifying'
    drivers: tuple[str,str] = ('LEC','VER')
    part: str = 'Q3'


CIRCUITS = (
    Circuit3D('paul_ricard','Paul Ricard','French Grand Prix','telemetry',2022),
    Circuit3D('singapore','Singapore / Marina Bay','Singapore Grand Prix','telemetry',2024,drivers=('NOR','VER')),
    Circuit3D('monaco','Monaco','Monaco Grand Prix','telemetry',2024,drivers=('LEC','PIA')),
    Circuit3D('austria','Red Bull Ring','Austrian Grand Prix','telemetry',2025,
              session='Race',drivers=('LEC','NOR'),part='All'),
    Circuit3D('bahrain','Bahrain','Bahrain Grand Prix','telemetry',2024,drivers=('VER','LEC')),
    Circuit3D('monza','Monza','Italian Grand Prix','telemetry',2024,drivers=('LEC','NOR')),
    Circuit3D('silverstone','Silverstone','British Grand Prix','telemetry',2022),
    Circuit3D('spa','Spa-Francorchamps','Belgian Grand Prix','telemetry',2025,
              session='Race',drivers=('LEC','PIA'),part='All'),
    Circuit3D('melbourne','Albert Park','Australian Grand Prix','telemetry',2024),
    Circuit3D('shanghai','Shanghai','Chinese Grand Prix','telemetry',2024),
    Circuit3D('suzuka','Suzuka','Japanese Grand Prix','telemetry',2024),
    Circuit3D('jeddah','Jeddah','Saudi Arabian Grand Prix','telemetry',2024),
    Circuit3D('miami','Miami','Miami Grand Prix','telemetry',2024),
    Circuit3D('montreal','Montreal','Canadian Grand Prix','telemetry',2024),
    Circuit3D('barcelona','Barcelona-Catalunya','Barcelona-Catalunya Grand Prix','telemetry',2026),
    Circuit3D('spain','Spain','Spanish Grand Prix','telemetry',2024),
    Circuit3D('hungaroring','Hungaroring','Hungarian Grand Prix','telemetry',2024),
    Circuit3D('zandvoort','Zandvoort','Dutch Grand Prix','telemetry',2024),
    Circuit3D('baku','Baku','Azerbaijan Grand Prix','telemetry',2024),
    Circuit3D('austin','Circuit of the Americas','United States Grand Prix','telemetry',2024),
    Circuit3D('mexico','Mexico City','Mexico City Grand Prix','telemetry',2024),
    Circuit3D('interlagos','Interlagos','São Paulo Grand Prix','telemetry',2024),
    Circuit3D('vegas','Las Vegas','Las Vegas Grand Prix','telemetry',2024),
    Circuit3D('lusail','Lusail','Qatar Grand Prix','telemetry',2024),
    Circuit3D('yas_marina','Yas Marina','Abu Dhabi Grand Prix','telemetry',2024),
    Circuit3D('imola','Imola','Emilia Romagna Grand Prix','telemetry',2024),
    Circuit3D('hockenheim','Hockenheim','German Grand Prix','telemetry',2019),
    Circuit3D('sochi','Sochi','Russian Grand Prix','telemetry',2021),
    Circuit3D('istanbul','Istanbul Park','Turkish Grand Prix','telemetry',2021),
    Circuit3D('portimao','Portimão','Portuguese Grand Prix','telemetry',2021),
    Circuit3D('mugello','Mugello','Tuscan Grand Prix','telemetry',2020),
    Circuit3D('nurburgring','Nürburgring','Eifel Grand Prix','telemetry',2020),
    Circuit3D('sakhir','Sakhir Outer','Sakhir Grand Prix','telemetry',2020),
    Circuit3D('brazil','Interlagos','Brazilian Grand Prix','telemetry',2019),
    Circuit3D('mexican','Mexico City','Mexican Grand Prix','telemetry',2019),
    Circuit3D('anniversary','Silverstone','70th Anniversary Grand Prix','telemetry',2020),
    Circuit3D('styrian','Red Bull Ring','Styrian Grand Prix','telemetry',2021),
)


def circuit_for(year,event):
    event={'Sao Paulo Grand Prix':'São Paulo Grand Prix',
           'Saudi Arabia Grand Prix':'Saudi Arabian Grand Prix'}.get(event,event)
    for circuit in CIRCUITS:
        if event == circuit.event:
            valid = 2018<=int(year)<=2022 if circuit.backend=='asset' else 2018<=int(year)<=date.today().year
            return circuit if valid else None
    return None


def environment_options(year,event):
    circuit=circuit_for(year,event)
    if circuit is None:return ()
    return ('Telemetry-built',)


def resolve_environment(year,event,environment='Auto'):
    options=environment_options(year,event)
    if not options:raise ValueError('No supported 3D circuit for this year/event.')
    if environment=='Auto':return options[0]
    if environment not in options:raise ValueError('Imported circuit models are disabled. Choose Telemetry-built.')
    return environment


def presentation(year,event,environment=None):
    circuit=circuit_for(year,event)
    if circuit and circuit.backend=='asset' and environment!='Telemetry-built':
        return {'name':circuit.name,'backend':'asset',
                'credit':'Circuit: narlankaaditya / CC BY 4.0 · '+CAR_CREDIT,
                'description':'Calibrated licensed circuit · stylized materials/scenery'}
    return {'name':circuit.name if circuit else event.replace(' Grand Prix',''),
            'backend':'telemetry','credit':'Telemetry-built circuit · '+CAR_CREDIT,
            'description':'Telemetry layout · illustrative kerbs · estimated grade / flat fallback'}

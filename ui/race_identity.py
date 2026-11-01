"""Small presentation helpers for race and driver identity cards."""
import base64
import html
from pathlib import Path
from urllib.parse import urlparse
import re

ROOT=Path(__file__).resolve().parents[1]
VENUES={
    'Australian':('au','Australia','Albert Park'), 'Chinese':('cn','China','Shanghai'),
    'Japanese':('jp','Japan','Suzuka'), 'Bahrain':('bh','Bahrain','Sakhir'),
    'Saudi Arabian':('sa','Saudi Arabia','Jeddah'), 'Saudi Arabia':('sa','Saudi Arabia','Jeddah'),
    'Miami':('us','United States','Miami'), 'Canadian':('ca','Canada','Montréal'),
    'Monaco':('mc','Monaco','Monte Carlo'), 'Barcelona-Catalunya':('es','Spain','Barcelona'),
    'Barcelona':('es','Spain','Barcelona'), 'Spanish':('es','Spain','Spain'),
    'Austrian':('at','Austria','Spielberg'), 'British':('gb','United Kingdom','Silverstone'),
    'Belgian':('be','Belgium','Spa-Francorchamps'), 'Hungarian':('hu','Hungary','Budapest'),
    'Dutch':('nl','Netherlands','Zandvoort'), 'Italian':('it','Italy','Monza'),
    'Azerbaijan':('az','Azerbaijan','Baku'), 'Singapore':('sg','Singapore','Marina Bay'),
    'United States':('us','United States','Austin'), 'Mexico City':('mx','Mexico','Mexico City'),
    'Mexican':('mx','Mexico','Mexico City'), 'São Paulo':('br','Brazil','Interlagos'),
    'Sao Paulo':('br','Brazil','Interlagos'), 'Brazilian':('br','Brazil','Interlagos'),
    'Las Vegas':('us','United States','Las Vegas'), 'Qatar':('qa','Qatar','Lusail'),
    'Abu Dhabi':('ae','United Arab Emirates','Yas Marina'), 'French':('fr','France','Paul Ricard'),
    'Emilia Romagna':('it','Italy','Imola'), 'German':('de','Germany','Hockenheim'),
    'Eifel':('de','Germany','Nürburgring'), 'Turkish':('tr','Türkiye','Istanbul'),
    'Portuguese':('pt','Portugal','Portimão'), 'Russian':('ru','Russia','Sochi'),
    'Tuscan':('it','Italy','Mugello'), 'Sakhir':('bh','Bahrain','Sakhir Outer'),
    'Styrian':('at','Austria','Spielberg'), '70th Anniversary':('gb','United Kingdom','Silverstone'),
}


def venue(event):
    title=event.removesuffix(' Grand Prix')
    return VENUES.get(title,('',title,title))


def event_label(event):
    _,_,place=venue(event)
    return f'{place} · {event.removesuffix(" Grand Prix")}'


def track_card(event,year,session,lighting):
    code,country,place=venue(event)
    flag=ROOT/'assets'/'flags'/f'{code}.png'
    image=(f'<img src="data:image/png;base64,{base64.b64encode(flag.read_bytes()).decode()}" alt="{html.escape(country)} flag">'
           if flag.is_file() else f'<span class="rh-country-code">{html.escape(code.upper())}</span>')
    return (f'<div class="rh-race-ticket"><div class="rh-race-identity">{image}<div><small>{html.escape(country)} / {year}</small>'
            f'<h2>{html.escape(place)}</h2><p>{html.escape(event)}</p></div></div>'
            f'<div class="rh-ticket-tags"><span>{html.escape(session)}</span><span>{html.escape(lighting.title())} race</span></div></div>')


def driver_card(code,entry,slot):
    color=str(entry.get('color','')).lstrip('#')
    color='#'+color if re.fullmatch('[0-9a-fA-F]{6}',color) else '#6bd9ca'
    name=str(entry.get('name',code));team=str(entry.get('team',''))
    url=str(entry.get('portrait',''))
    safe=urlparse(url)
    # Timing feeds supply a 93px thumbnail. Use the same portrait at card and
    # high-density sizes, preserving the feed's driver/season identity.
    srcset=''
    if safe.hostname=='media.formula1.com' and '.transform/1col/' in url:
        url=url.replace('.transform/1col/','.transform/4col/')
        retina=url.replace('.transform/4col/','.transform/8col/')
        srcset=f' srcset="{html.escape(url,quote=True)} 1x, {html.escape(retina,quote=True)} 2x"'
    portrait=(f'<img src="{html.escape(url,quote=True)}"{srcset} alt="{html.escape(name)}" loading="lazy">'
              if safe.scheme=='https' and safe.netloc else '')
    return (f'<div class="rh-driver-card" style="--driver-color:{color}"><div class="rh-driver-copy"><small>{slot}</small>'
            f'<strong>{html.escape(code)}</strong><h3>{html.escape(name)}</h3><p>{html.escape(team)}</p>'
            f'<span>{str(len(entry["laps"]))+" timed laps" if "laps" in entry else ""}</span></div><div class="rh-driver-photo">'
            f'<span class="rh-driver-initial">{html.escape(code)}</span>{portrait}</div></div>')

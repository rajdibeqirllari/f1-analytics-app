"""2026 field: one chassis spec per constructor (geometry archetype, paint, sponsors, number style).

Checklist = the 2026 entry list as the session metadata reports it (2026 Las Vegas GP, FastF1): 11 constructors,
22 drivers. Liveries from the January-February 2026 launches as described by the sources in SOURCES (dated); shapes
are parametric variants of one 2026-rules template (3.40 m wheelbase, 1.90 m wide) tuned per team from launch and
race-weekend imagery and published technical analysis. Sponsor identities are set as wordmarks (type in the brand
colours); official logo artwork is NOT reproduced and is listed per team in MISSING_ART.

Colours are sRGB hex; the Blender builder converts them to linear for vertex colours.
"""

SOURCES = {
    'liveries': [
        ('The Race, "Ranking the 2026 F1 liveries" (Feb 2026)', 'https://www.the-race.com/formula-1/ranking-2026-f1-liveries-worst-to-best/'),
        ('theScore, "Ranking the 2026 Formula 1 liveries" (Feb 2026)', 'https://www.thescore.com/formula1/news/3458807/amp'),
        ('Crash.net, all 2026 cars and liveries (Feb 2026)', 'https://www.crash.net/f1/news/1088479/1/f1-2026-every-teams-car-and-livery-revealed-so-far'),
        ('RTR Sports, F1 liveries and sponsor visibility (2026)', 'https://rtrsports.com/en/blog/f1-liveries/'),
        ('Formula1.com, Alpine A526 first look (23 Jan 2026)', 'https://www.formula1.com/en/latest/article/first-look-alpine-unveil-new-car-ahead-of-2026-f1-season.4sRaEq3lWrZqcMxVCQ6Ub5'),
        ('Formula1.com, Red Bull 2026 livery first look (15 Jan 2026)', 'https://www.formula1.com/en/latest/article/first-look-red-bull-unveil-striking-new-livery-for-2026-f1-season.61MNwo6zMoxUtOAjS8JH0S'),
        ('Motorsport.com, Mercedes W17 livery (22 Jan 2026)', 'https://www.motorsport.com/f1/news/mercedes-unveils-w17-livery-as-new-stripes-draw-mixed-reaction-ahead-of-2026-f1-season/10792098/'),
        ('Photos: RB22 Japan-update side comparison (Apr 2026); W17 Hungarian GP, Russell (26 Jul 2026)', ''),
    ],
    'numbers': [('Formula1.com, all 2026 driver numbers', 'https://www.formula1.com/en/latest/article/all-the-2026-f1-driver-numbers-confirmed-in-full.5rh7o9mPntG7NerzVk9onc.5rh7o9mPntG7NerzVk9onc/'),
                ('Session metadata: 2026 Las Vegas GP (FastF1 cache) for numbers, codes and team names', '')],
}

FONTS = {   # Windows system fonts for wordmarks (rendered into our own textures), bundled OFL fonts for numbers
    'sans': 'C:/Windows/Fonts/arialbd.ttf', 'black': 'C:/Windows/Fonts/ariblk.ttf', 'cond': 'C:/Windows/Fonts/bahnschrift.ttf',
    'impact': 'C:/Windows/Fonts/impact.ttf', 'serif': 'C:/Windows/Fonts/georgiab.ttf', 'segoe': 'C:/Windows/Fonts/seguibl.ttf',
    'franklin': 'C:/Windows/Fonts/framd.ttf', 'gill': 'C:/Windows/Fonts/GILSANUB.TTF', 'verdana': 'C:/Windows/Fonts/verdanab.ttf',
    'trebuchet': 'C:/Windows/Fonts/trebucbd.ttf', 'tahoma': 'C:/Windows/Fonts/tahomabd.ttf',
}

# Geometry archetypes (applied to the 2026 template in build_field.py). Values describe visible features only.
#   nose: tip height/length; pods: 'high_flat' | 'ramp' | 'bathtub' | 'wedge' | 'long_slim'; airbox: 'round' | 'tri' | 'oval' | 'tall_tri'
#   rw: 'swan' | 'twin' | 'single'; fin: engine-cover fin; walls: diffuser sidewalls; fw_endfin: front endplate foot fin
TEAMS = {
    'mclaren': dict(
        chassis='McLaren MCL40', team='McLaren', aliases=[r'^mclaren'], drivers={'NOR': 1, 'PIA': 81},
        geom=dict(nose=('mid', 2.70), pods='ramp', inlet='letterbox', airbox='oval', rw='swan', fin=False, walls=True, fw_endfin=True, tub=0.0),
        paint=dict(base='#FF8000', second='#1E1F24', accent='#47C7FC', zones=['lower_dark', 'engine_rear_dark', 'wings_dark', 'halo_dark', 'nose_tip_dark']),
        sponsors=[('pod', 'Mastercard', 'black', '#1E1F24'), ('engine', 'OKX', 'black', '#FFFFFF'), ('rw_top', 'Mastercard', 'black', '#FF8000'),
                  ('nose_side', 'Gemini', 'sans', '#FFFFFF'), ('rw_ep', 'Google', 'sans', '#FFFFFF'), ('fw_ep', 'DP World', 'sans', '#FFFFFF')],
        number=dict(font='shoulders', fill='#1E1F24', outline='#FFFFFF'), finish='gloss',
        notes='Papaya with anthracite lower body and wings (launch); #1 on Norris. Partner list beyond Mastercard/Google Gemini is from 2025 and needs confirmation.'),
    'ferrari': dict(
        chassis='Ferrari SF-26', team='Ferrari', aliases=[r'^(scuderia )?ferrari'], drivers={'LEC': 16, 'HAM': 44},
        geom=dict(nose=('low', 2.76), pods='wedge', inlet='tall', airbox='oval', rw='single', fin=True, walls=True, fw_endfin=False, tub=0.0),
        paint=dict(base='#D40000', second='#F4F4F2', accent='#1A1A1A', zones=['engine_white_band', 'airbox_white', 'wings_dark', 'halo_dark']),
        sponsors=[('engine', 'HP', 'segoe', '#0096D6'), ('rw_top', 'HP', 'segoe', '#FFFFFF'), ('pod', 'Shell', 'black', '#FFD500'),
                  ('nose_side', 'UniCredit', 'sans', '#FFFFFF'), ('rw_ep', 'IBM', 'black', '#FFFFFF'), ('fw_ep', 'Santander', 'sans', '#FFFFFF')],
        number=dict(font='serif', fill='#FFFFFF', outline=None), finish='satin',
        notes='Red with white band inspired by the 312T / 2016-18 cars, blue HP logo (title partner). Shell/UniCredit/IBM/Santander assumed carried over from 2025.'),
    'red_bull': dict(
        chassis='Red Bull RB22', team='Red Bull Racing', aliases=[r'^(oracle )?red bull( racing)?$'], drivers={'VER': 3, 'HAD': 6},
        geom=dict(nose=('arrow', 2.74), pods='bathtub', inlet='letterbox', airbox='tall_tri', rw='twin', fin=False, walls=False, fw_endfin=False, tub=0.03),
        paint=dict(base='#1B2A6B', second='#1B2A6B', accent='#F8C21A', zones=['airbox_yellow', 'nose_tip_yellow', 'red_pinstripe', 'wings_dark']),
        sponsors=[('pod', 'ORACLE', 'black', '#FFFFFF'), ('engine', 'Red Bull', 'black', '#DB0A40'), ('rw_ep', 'Mobil 1', 'black', '#FFFFFF'),
                  ('nose_side', 'CARLYLE', 'sans', '#FFFFFF'), ('rw_top', 'ORACLE', 'black', '#FFFFFF'), ('fw_ep', 'Ford', 'serif', '#FFFFFF')],
        number=dict(font='shoulders', fill='#FFFFFF', outline='#DB0A40'), finish='gloss',
        notes='Gloss metallic navy, yellow on airbox/nose (launch 15 Jan 2026; Japan update photo Apr 2026). The charging-bull and sun logos are not reproduced.'),
    'mercedes': dict(
        chassis='Mercedes W17', team='Mercedes', aliases=[r'^mercedes'], drivers={'RUS': 63, 'ANT': 12},
        geom=dict(nose=('high', 2.66), pods='high_flat', inlet='tall', airbox='round', rw='swan', fin=True, walls=True, fw_endfin=True, tub=0.0),
        paint=dict(base='#0B0C0E', second='#7C8189', accent='#00A19C', zones=['engine_silver', 'teal_lines', 'wings_dark']),
        sponsors=[('rw_top', 'PETRONAS', 'black', '#00A19C'), ('airbox', 'Microsoft', 'segoe', '#FFFFFF'), ('pod', 'PETRONAS', 'black', '#00A19C'),
                  ('nose_side', 'AMG', 'black', '#FFFFFF'), ('rw_ep', 'PETRONAS', 'black', '#FFFFFF'), ('fw_ep', 'UBS', 'serif', '#FFFFFF')],
        number=dict(font='shoulders', fill='#00A19C', outline='#FFFFFF'), finish='satin',
        notes='Black and silver with Petronas teal (Hungarian GP photo, 26 Jul 2026); Microsoft on the airbox (Wikipedia W17). The rhombus/star patterns are not reproduced.'),
    'aston_martin': dict(
        chassis='Aston Martin AMR26', team='Aston Martin', aliases=[r'^aston martin'], drivers={'ALO': 14, 'STR': 18},
        geom=dict(nose=('mid', 2.72), pods='long_slim', inlet='tall', airbox='oval', rw='single', fin=True, walls=True, fw_endfin=True, tub=0.0),
        paint=dict(base='#00483A', second='#0B1F1A', accent='#CEDC00', zones=['lime_stripe', 'wings_dark', 'halo_dark']),
        sponsors=[('pod', 'Aramco', 'gill', '#FFFFFF'), ('rw_top', 'Aramco', 'gill', '#FFFFFF'), ('engine', 'Cognizant', 'sans', '#FFFFFF'),
                  ('nose_side', 'HONDA', 'black', '#FFFFFF'), ('rw_ep', 'Aramco', 'gill', '#CEDC00'), ('fw_ep', 'Valvoline', 'black', '#FFFFFF')],
        number=dict(font='shoulders', fill='#CEDC00', outline=None), finish='satin',
        notes='British Racing Green with lime, Aramco title partner (Feb 2026). Honda power unit; Cognizant/Valvoline from 2025 need confirmation.'),
    'alpine': dict(
        chassis='Alpine A526', team='Alpine', aliases=[r'^(bwt )?alpine'], drivers={'GAS': 10, 'COL': 43},
        geom=dict(nose=('mid', 2.70), pods='ramp', inlet='letterbox', airbox='round', rw='swan', fin=False, walls=True, fw_endfin=False, tub=0.0),
        paint=dict(base='#0A3D91', second='#061F4A', accent='#F363B4', zones=['nose_top_pink', 'engine_pink_strip', 'halo_pink', 'fw_pink']),
        sponsors=[('pod', 'BWT', 'black', '#F363B4'), ('rw_top', 'BWT', 'black', '#FFFFFF'), ('engine', 'MSC Cruises', 'serif', '#FFFFFF'),
                  ('nose_side', 'BWT', 'black', '#0A3D91'), ('rw_ep', 'Alpine', 'gill', '#FFFFFF'), ('fw_ep', 'MSC', 'serif', '#FFFFFF')],
        number=dict(font='shoulders', fill='#FFFFFF', outline='#F363B4'), finish='gloss',
        notes='Deep blue with BWT pink on nose top, engine strip, halo and front wing (launch, 23 Jan 2026); MSC Cruises partner.'),
    'williams': dict(
        chassis='Williams FW48', team='Williams', aliases=[r'^(atlassian )?williams'], drivers={'ALB': 23, 'SAI': 55},
        geom=dict(nose=('high', 2.68), pods='high_flat', inlet='letterbox', airbox='tri', rw='twin', fin=True, walls=True, fw_endfin=True, tub=0.0),
        paint=dict(base='#1868DB', second='#0B1E4A', accent='#FFFFFF', zones=['lower_dark', 'wings_dark']),
        sponsors=[('pod', 'ATLASSIAN', 'black', '#FFFFFF'), ('rw_top', 'ATLASSIAN', 'black', '#FFFFFF'), ('engine', 'DURACELL', 'black', '#FFFFFF'),
                  ('nose_side', 'Komatsu', 'black', '#FFFFFF'), ('rw_ep', 'Williams', 'serif', '#FFFFFF'), ('fw_ep', 'Michelob', 'serif', '#FFFFFF')],
        number=dict(font='shoulders', fill='#FFFFFF', outline='#0B1E4A'), finish='gloss',
        notes='Atlassian cobalt as one bright block over navy (Feb 2026). Duracell/Komatsu/Michelob Ultra from 2025 need confirmation.'),
    'racing_bulls': dict(
        chassis='Racing Bulls VCARB 03', team='Racing Bulls', aliases=[r'^(visa cash app )?(racing bulls|rb)( f1 team)?$', r'^rb$'], drivers={'LAW': 30, 'LIN': 41},
        geom=dict(nose=('arrow', 2.72), pods='bathtub', inlet='letterbox', airbox='tall_tri', rw='twin', fin=False, walls=False, fw_endfin=False, tub=0.025),
        paint=dict(base='#F4F5F7', second='#1634CC', accent='#ED1C24', zones=['blue_lower', 'blue_engine_sweep', 'wings_dark']),
        sponsors=[('pod', 'VISA', 'black', '#1634CC'), ('engine', 'Cash App', 'black', '#00D632'), ('rw_top', 'VISA', 'black', '#FFFFFF'),
                  ('nose_side', 'Cash App', 'black', '#00D632'), ('rw_ep', 'VISA', 'black', '#FFFFFF'), ('fw_ep', 'Ford', 'serif', '#1634CC')],
        number=dict(font='shoulders', fill='#1634CC', outline='#FFFFFF'), finish='gloss',
        notes='White base with blue accents (Red Bull Ford power), Visa and Cash App on sidepods and engine cover (Feb 2026).'),
    'haas': dict(
        chassis='Haas VF-26', team='Haas', aliases=[r'^(tgr |moneygram )?haas'], drivers={'BEA': 87, 'CAM': 51},
        geom=dict(nose=('low', 2.74), pods='wedge', inlet='tall', airbox='tri', rw='single', fin=True, walls=True, fw_endfin=False, tub=0.0),
        paint=dict(base='#F2F2F2', second='#1A1A1A', accent='#E10600', zones=['black_engine', 'red_sweep', 'wings_dark']),
        sponsors=[('pod', 'TOYOTA GAZOO Racing', 'black', '#1A1A1A'), ('rw_top', 'TGR', 'black', '#FFFFFF'), ('engine', 'HAAS', 'black', '#E10600'),
                  ('nose_side', 'TOYOTA', 'black', '#E10600'), ('rw_ep', 'HAAS', 'black', '#FFFFFF'), ('fw_ep', 'TGR', 'black', '#FFFFFF')],
        number=dict(font='shoulders', fill='#E10600', outline='#1A1A1A'), finish='satin',
        notes='White dominant with red and black, Toyota Gazoo Racing title partner replacing MoneyGram (Feb 2026).'),
    'audi': dict(
        chassis='Audi R26', team='Audi', aliases=[r'^(revolut )?audi', r'^(stake |kick )?sauber', r'^kick sauber'], drivers={'HUL': 27, 'BOR': 5},
        geom=dict(nose=('mid', 2.76), pods='long_slim', inlet='letterbox', airbox='oval', rw='single', fin=True, walls=True, fw_endfin=True, tub=0.0),
        paint=dict(base='#A7A9AC', second='#141414', accent='#E10619', zones=['black_lower', 'red_accent_band', 'wings_dark']),
        sponsors=[('pod', 'Revolut', 'segoe', '#141414'), ('rw_top', 'Revolut', 'segoe', '#FFFFFF'), ('engine', 'AUDI', 'franklin', '#141414'),
                  ('nose_side', 'AUDI', 'franklin', '#E10619'), ('rw_ep', 'Revolut', 'segoe', '#FFFFFF'), ('fw_ep', 'adidas', 'sans', '#FFFFFF')],
        number=dict(font='shoulders', fill='#E10619', outline='#141414'), finish='satin',
        notes="Audi's first works livery: titanium silver, black and red, Revolut title partner (Feb 2026). The four-ring logo is not reproduced."),
    'cadillac': dict(
        chassis='Cadillac (2026)', team='Cadillac', aliases=[r'^cadillac'], drivers={'BOT': 77, 'PER': 11},
        geom=dict(nose=('high', 2.70), pods='high_flat', inlet='tall', airbox='round', rw='swan', fin=True, walls=True, fw_endfin=True, tub=0.0),
        paint=dict(base='#D9DBDE', second='#0D0D0F', accent='#B8975A', zones=['split_sides']),
        sponsors=[('pod', 'TWG AI', 'black', '#B8975A'), ('engine', 'CADILLAC', 'franklin', '#B8975A'), ('rw_top', 'CADILLAC', 'franklin', '#FFFFFF'),
                  ('nose_side', 'TOMMY HILFIGER', 'sans', '#FFFFFF'), ('rw_ep', 'JIM BEAM', 'serif', '#FFFFFF'), ('fw_ep', 'IFS', 'black', '#FFFFFF')],
        number=dict(font='shoulders', fill='#B8975A', outline='#0D0D0F'), finish='gloss',
        notes='Debut season: two-sided design, grey-white on one flank and black on the other (which flank is which is assumed: white on the left); TWG AI primary partner, Tommy Hilfiger, Jim Beam, IFS (Feb 2026).'),
}

# Official artwork still missing (only wordmarks are rendered): logos, crests, patterns.
MISSING_ART = {
    'mclaren': ['McLaren speedmark', 'Mastercard circles logo', 'Google Gemini star logo'],
    'ferrari': ['Prancing horse shield', 'HP logo roundel', 'Shell pecten'],
    'red_bull': ['Charging bulls + sun', 'Ford oval', 'Mobil 1 pegasus mark'],
    'mercedes': ['Three-pointed star', 'AMG rhombus pattern', 'Petronas logo mark'],
    'aston_martin': ['Aston Martin wings', 'Aramco logo mark', 'Honda H'],
    'alpine': ['Alpine A logo', 'BWT logo mark'],
    'williams': ['Williams W', 'Atlassian logo mark'],
    'racing_bulls': ['Bulls logo', 'Visa and Cash App logo marks'],
    'haas': ['Haas logo', 'Toyota Gazoo Racing logo'],
    'audi': ['Four rings', 'Revolut logo mark'],
    'cadillac': ['Cadillac crest', 'TWG logo'],
}

# 2025 constructor identities -> 2026 constructor (for the labelled preview on 2025 sessions)
PREVIEW_FROM_2025 = {r'^(stake |kick )?sauber|^kick sauber': 'audi', r'^(visa cash app )?(racing bulls|rb)': 'racing_bulls'}

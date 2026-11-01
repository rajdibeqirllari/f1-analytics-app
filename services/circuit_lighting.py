"""Race-venue presentation lighting, separate from chase-camera selection.

This follows the Grand Prix's usual race setting, not individual practice times.
"""


def race_lighting(year, event):
    if event == 'Abu Dhabi Grand Prix':
        return 'twilight'
    first_night = {'Singapore Grand Prix': 2008, 'Bahrain Grand Prix': 2014,
                   'Saudi Arabian Grand Prix': 2021, 'Saudi Arabia Grand Prix': 2021,
                   'Qatar Grand Prix': 2021, 'Las Vegas Grand Prix': 2023,
                   'Sakhir Grand Prix': 2020}
    return 'night' if event in first_night and int(year) >= first_night[event] else 'day'

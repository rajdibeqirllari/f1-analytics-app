import f1radio
from pathlib import Path

BASE_DIR = Path(__file__).parent
RADIO_DIR = BASE_DIR / "outputs" / "radio"
RADIO_DIR.mkdir(parents=True, exist_ok=True)
f1radio.set_cache_dir(str(RADIO_DIR / "cache"))

# Load the 2024 Italian Grand Prix race session
session = f1radio.load(2024, "Monza", "R")

print(f"Total radio clips: {len(session.clips)}")
print()

# Display the first 10 radio messages with race context
for clip in session.clips[:10]:
    ctx = clip.context

    print(
        f"{clip.driver} | "
        f"Lap {clip.lap} | "
        f"P{ctx.position} | "
        f"Tyre: {ctx.compound} | "
        f"Age: {ctx.tyre_age}"
    )

# Export all enriched radio information
session.export_csv(str(RADIO_DIR / "monza_radio.csv"))
session.export_json(str(RADIO_DIR / "monza_radio.json"))

print()
print(f"Created {RADIO_DIR / 'monza_radio.csv'} and {RADIO_DIR / 'monza_radio.json'}")

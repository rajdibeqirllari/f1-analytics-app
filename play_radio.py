import f1radio
from pathlib import Path

BASE_DIR = Path(__file__).parent
RADIO_DIR = BASE_DIR / "outputs" / "radio"
RADIO_DIR.mkdir(parents=True, exist_ok=True)
f1radio.set_cache_dir(str(RADIO_DIR / "cache"))

session = f1radio.load(2024, "Monza", "R")

# Find the first Verstappen radio clip
clips = session.clips.filter(driver="VER")

if not clips:
    print("No VER radio clips found.")
else:
    clip = clips[0]

    print(f"Playing: {clip.driver} | Lap {clip.lap} | P{clip.context.position}")
    clip.play()

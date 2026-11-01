"""Read-only structural checks for downloaded 3D assets; never runs asset code."""
from pathlib import Path
import hashlib
import json
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1] / "assets" / "3d" / "incoming"


def inspect(path):
    result = {"file": path.name, "bytes": path.stat().st_size}
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    result["sha256"] = digest.hexdigest()
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            for name in names:
                # Windows handles backslashes as separators as well.
                destination = (ROOT / name.replace("\\", "/")).resolve()
                if not destination.is_relative_to(ROOT.resolve()):
                    raise ValueError(f"Unsafe archive path: {name}")
            result["entries"] = len(names)
            result["model_files"] = [n for n in names if Path(n).suffix.lower()
                                     in {".blend", ".glb", ".fbx", ".obj"}]
            result["license_files"] = [n for n in names if "license" in n.lower()]
            result["crc_error"] = archive.testzip()
    elif path.suffix == ".glb":
        with path.open("rb") as stream:
            magic, version, length = struct.unpack("<4sII", stream.read(12))
            if magic != b"glTF" or version != 2 or length != path.stat().st_size:
                raise ValueError("Invalid GLB header")
            size, kind = struct.unpack("<II", stream.read(8))
            if kind != 0x4E4F534A:
                raise ValueError("Missing GLB JSON chunk")
            scene = json.loads(stream.read(size))
            result["meshes"] = len(scene.get("meshes", []))
            result["nodes"] = len(scene.get("nodes", []))
            result["materials"] = len(scene.get("materials", []))
            result["external_uris"] = [item["uri"] for group in ("images", "buffers")
                                       for item in scene.get(group, [])
                                       if "uri" in item and not item["uri"].startswith("data:")]
            result["position_bounds"] = [{k: a.get(k) for k in ("min", "max")}
                                         for a in scene.get("accessors", [])
                                         if a.get("type") == "VEC3" and "min" in a][:6]
    else:
        with path.open("rb") as stream:
            result["header"] = repr(stream.read(32))
    return result


if __name__ == "__main__":
    print(json.dumps([inspect(p) for p in sorted(ROOT.iterdir()) if p.is_file()], indent=2))

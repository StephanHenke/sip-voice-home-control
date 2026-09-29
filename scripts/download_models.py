"""Download fixed model versions at image build time, never during a call."""

from pathlib import Path
import json
import hashlib
import urllib.request
import zipfile

root = Path("/models")
root.mkdir(parents=True, exist_ok=True)
manifest = {}


def fetch(url: str, path: Path):
    with urllib.request.urlopen(url, timeout=120) as response, path.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    manifest[path.name] = {"url": url, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


archive = root / "vosk-model-small-de-0.15.zip"
fetch("https://alphacephei.com/vosk/models/vosk-model-small-de-0.15.zip", archive)
with zipfile.ZipFile(archive) as model:
    for member in model.infolist():
        target = (root / member.filename).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError("Unsafe model archive path")
    model.extractall(root)
archive.unlink()

# Fixed revision instead of the mutable main branch.
revision = "375a0fe641dea077c2a47b4e9a056d6da521eed3"  # v1.0.0
base = f"https://huggingface.co/rhasspy/piper-voices/resolve/{revision}/de/de_DE/thorsten/medium"
for filename in ("de_DE-thorsten-medium.onnx", "de_DE-thorsten-medium.onnx.json", "MODEL_CARD"):
    fetch(f"{base}/{filename}", root / filename)
(root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

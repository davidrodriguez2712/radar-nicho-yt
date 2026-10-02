"""Install the reviewed embedding artifacts at an immutable revision with hash checks."""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

MODEL_ID = "sentence-transformers/paraphrase-MiniLM-L3-v2"
REVISION = "4ca70771034acceecb2e72475f72050fcdde4ddc"
MODELS = {
    "amd64": (
        "onnx/model_quint8_avx2.onnx",
        "7b411e18f5974428b388be5667cf76d57c2a52968e1d6b0153a30a8ccfb34204",
    ),
    "arm64": (
        "onnx/model_qint8_arm64.onnx",
        "44a2d6852c28e7a4cff4d77a8bc8d5ca2a8b38884c1fa746e6652d830109e0c2",
    ),
}
TOKENIZER_SHA256 = "a9576e4dadfe7f78f071a1c00ba6902cc83ec6ed7e9b590ee974950bd4d54393"


def download(url: str, destination: Path, expected_sha256: str) -> None:
    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "NicheRadar model installer"})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != expected_sha256:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("embedding artifact hash mismatch")
    temporary.replace(destination)


target = Path(sys.argv[1] if len(sys.argv) > 1 else "/models/paraphrase-MiniLM-L3-v2")
architecture = sys.argv[2] if len(sys.argv) > 2 else "amd64"
if architecture not in MODELS:
    raise SystemExit("unsupported embedding architecture")
target.mkdir(parents=True, exist_ok=True)
files = {
    "model.onnx": MODELS[architecture],
    "tokenizer.json": ("tokenizer.json", TOKENIZER_SHA256),
}
for local_name, (remote_name, expected_sha256) in files.items():
    url = f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{remote_name}?download=true"
    download(url, target / local_name, expected_sha256)
(target / "manifest.json").write_text(
    json.dumps(
        {
            "model_id": MODEL_ID,
            "revision": REVISION,
            "format": f"onnx-qint8-{architecture}",
            "architecture": architecture,
            "files": {name: checksum for name, (_, checksum) in files.items()},
        },
        sort_keys=True,
    )
)

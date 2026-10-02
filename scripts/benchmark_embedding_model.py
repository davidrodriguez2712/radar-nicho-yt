"""Measure the pinned local ONNX model without downloading or printing external text."""

import json
import resource
import sys
import time
from pathlib import Path

from nicheradar.topics.grouping import LocalOnnxEmbedder

MODEL_VERSION = "paraphrase-MiniLM-L3-v2@4ca70771034acceecb2e72475f72050fcdde4ddc-qint8-avx2"


def peak_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


directory = Path(sys.argv[1] if len(sys.argv) > 1 else "/models/paraphrase-MiniLM-L3-v2")
model = LocalOnnxEmbedder(directory, MODEL_VERSION, batch_size=16)
texts = [f"World cultures and language history example {index}" for index in range(200)]
encoded_at = time.monotonic()
vectors = model.encode(texts)
encoded_seconds = time.monotonic() - encoded_at
print(
    json.dumps(
        {
            "model_version": MODEL_VERSION,
            "model_bytes": (directory / "model.onnx").stat().st_size,
            "texts": len(texts),
            "dimensions": len(vectors[0]),
            "encode_seconds": round(encoded_seconds, 3),
            "peak_mib": round(peak_mib(), 1),
            "remote_code": False,
            "runtime": "onnxruntime-cpu",
        }
    )
)

"""Optional CPU model loading. No downloads or remote code execution."""

from functools import lru_cache
from pathlib import Path

from nicheradar.config import Settings
from nicheradar.topics.grouping import Embedder, LocalOnnxEmbedder


@lru_cache(maxsize=1)
def _load(directory: Path, version: str, batch_size: int) -> tuple[Embedder | None, str | None]:
    try:
        return LocalOnnxEmbedder(directory, version, batch_size), None
    except (ImportError, OSError, ValueError, RuntimeError):
        # Do not copy exceptions: they may contain local paths or external text.
        return None, "model_unavailable"


def configured_embedder(config: Settings) -> tuple[Embedder | None, str | None]:
    if config.embedding_model_directory is None or config.embedding_model_version is None:
        return None, "model_not_configured"
    return _load(
        config.embedding_model_directory,
        config.embedding_model_version,
        config.embedding_batch_size,
    )

import hashlib
import importlib
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Protocol

from nicheradar.integrations.contracts import Contract, Video


class Embedder(Protocol):
    version: str

    def encode(self, texts: list[str]) -> list[list[float]]: ...


class LocalOnnxEmbedder:
    def __init__(self, model_directory: Path, version: str, batch_size: int = 16):
        if not model_directory.is_dir() or not version or not 1 <= batch_size <= 32:
            raise ValueError("existing local model, version and bounded batch required")
        model_path = model_directory / "model.onnx"
        tokenizer_path = model_directory / "tokenizer.json"
        if not model_path.is_file() or not tokenizer_path.is_file():
            raise ValueError("local ONNX model and tokenizer required")
        numpy = importlib.import_module("numpy")
        onnxruntime = importlib.import_module("onnxruntime")
        tokenizers = importlib.import_module("tokenizers")
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        self.model = onnxruntime.InferenceSession(
            str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        self.tokenizer = tokenizers.Tokenizer.from_file(str(tokenizer_path))
        self.tokenizer.enable_truncation(max_length=128)
        self.tokenizer.enable_padding()
        self.numpy = numpy
        self.input_names = {item.name for item in self.model.get_inputs()}
        self.version = version
        self.batch_size = batch_size

    def encode(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            encoded = self.tokenizer.encode_batch(texts[start : start + self.batch_size])
            attention = self.numpy.asarray(
                [item.attention_mask for item in encoded], dtype=self.numpy.int64
            )
            inputs: dict[str, Any] = {
                "input_ids": self.numpy.asarray(
                    [item.ids for item in encoded], dtype=self.numpy.int64
                ),
                "attention_mask": attention,
            }
            if "token_type_ids" in self.input_names:
                inputs["token_type_ids"] = self.numpy.asarray(
                    [item.type_ids for item in encoded], dtype=self.numpy.int64
                )
            token_embeddings = self.model.run(None, inputs)[0]
            mask = attention[..., None]
            pooled = (token_embeddings * mask).sum(axis=1) / self.numpy.clip(
                mask.sum(axis=1), 1, None
            )
            norms = self.numpy.linalg.norm(pooled, axis=1, keepdims=True)
            if not self.numpy.isfinite(pooled).all() or (norms == 0).any():
                raise ValueError("invalid embedding dimensions/values")
            result.extend((pooled / norms).tolist())
        return result


def semantic_relevance(
    videos: tuple[Video, ...],
    *,
    query: str,
    embedder: Embedder,
    threshold: float,
    maximum_text_chars: int,
) -> tuple[set[str], dict[str, float]]:
    """Confirm high-similarity videos while leaving lower scores explicitly unknown."""
    if not query.strip() or not 0 < threshold <= 1 or not 100 <= maximum_text_chars <= 4000:
        raise ValueError("invalid semantic relevance bounds")
    unique = sorted({video.id: video for video in videos}.values(), key=lambda video: video.id)
    texts = [f"{video.title}\n{video.description or ''}"[:maximum_text_chars] for video in unique]
    vectors = embedder.encode([query, *texts])
    if len(vectors) != len(unique) + 1:
        raise ValueError("embedding response length mismatch")
    query_vector = tuple(vectors[0])
    scores = {
        video.id: cosine(query_vector, tuple(vector))
        for video, vector in zip(unique, vectors[1:], strict=True)
    }
    return {video_id for video_id, score in scores.items() if score >= threshold}, scores


class TopicGroup(Contract):
    key: str
    label: str | None
    member_ids: tuple[str, ...]
    method: str
    centroid: tuple[float, ...] | None = None
    ambiguous_matches: tuple[str, ...] = ()


def cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    if len(a) != len(b) or not a or not all(math.isfinite(value) for value in (*a, *b)):
        raise ValueError("invalid embedding dimensions/values")
    norm_a, norm_b = math.hypot(*a), math.hypot(*b)
    if not math.isfinite(norm_a) or not math.isfinite(norm_b):
        raise ValueError("invalid embedding norm")
    return (
        sum((x / norm_a) * (y / norm_b) for x, y in zip(a, b, strict=True))
        if norm_a and norm_b
        else 0
    )


def group_topics(
    videos: tuple[Video, ...],
    *,
    embedder: Embedder | None = None,
    minimum: int = 3,
    threshold: float = 0.8,
    maximum_videos: int = 200,
    previous: tuple[TopicGroup, ...] = (),
    maximum_text_chars: int = 2000,
) -> tuple[TopicGroup, ...]:
    if not 2 <= minimum <= maximum_videos or not 0 < threshold <= 1:
        raise ValueError("invalid grouping bounds")
    unique = sorted({video.id: video for video in videos}.values(), key=lambda video: video.id)
    if len(unique) > maximum_videos:
        raise ValueError("topic batch exceeds configured bound")
    if embedder is None:
        categories: dict[str, list[str]] = defaultdict(list)
        for video in unique:
            categories[video.category or "unknown"].append(video.id)
        return tuple(
            TopicGroup(
                key="provider-category:" + hashlib.sha256(category.encode()).hexdigest(),
                label=category if category != "unknown" else None,
                member_ids=tuple(ids),
                method="provider_category_fallback" if category != "unknown" else "unclassified",
            )
            for category, ids in sorted(categories.items())
        )
    if not 1 <= maximum_text_chars <= 4000 or len(previous) > 200:
        raise ValueError("text or history batch exceeds configured bound")
    if not unique:
        return ()
    vectors = embedder.encode(
        [f"{video.title}\n{video.description or ''}"[:maximum_text_chars] for video in unique]
    )
    if len(vectors) != len(unique):
        raise ValueError("embedding response length mismatch")
    groups: list[tuple[list[str], tuple[float, ...]]] = []
    for video, vector in zip(unique, vectors, strict=True):
        embedding = tuple(vector)
        if len(embedding) > 1024 or not any(embedding):
            raise ValueError("invalid embedding dimensions/values")
        cosine(embedding, embedding)
        norm = math.hypot(*embedding)
        embedding = tuple(value / norm for value in embedding)
        matches = [
            (index, cosine(embedding, centroid))
            for index, (_, centroid) in enumerate(groups)
            if cosine(embedding, centroid) >= threshold
        ]
        if len(matches) == 1:
            index, _ = matches[0]
            ids, centroid = groups[index]
            combined = tuple(
                (value * len(ids) + new) / (len(ids) + 1)
                for value, new in zip(centroid, embedding, strict=True)
            )
            groups[index] = ([*ids, video.id], combined)
        else:
            groups.append(([video.id], embedding))
    result = []
    for ids, centroid in groups:
        key = hashlib.sha256((embedder.version + ":" + ",".join(ids)).encode()).hexdigest()
        previous_matches = sorted(
            {
                group.key
                for group in previous
                if group.method == embedder.version
                and group.centroid
                and cosine(centroid, group.centroid) >= threshold
            }
        )
        supported = len(ids) >= minimum
        if len(previous_matches) > 1:
            key = hashlib.sha256(
                ("ambiguous:" + key + ":" + ",".join(previous_matches)).encode()
            ).hexdigest()
        result.append(
            TopicGroup(
                key=previous_matches[0] if supported and len(previous_matches) == 1 else key,
                label=None,
                member_ids=tuple(ids),
                centroid=centroid,
                method=embedder.version if supported else "noise",
                ambiguous_matches=tuple(previous_matches) if len(previous_matches) > 1 else (),
            )
        )
    # Two new clusters matching one old centroid are a split, not a safe merge.
    matched_keys = [group.key for group in result if group.key in {old.key for old in previous}]
    return tuple(
        group.model_copy(
            update={
                "key": hashlib.sha256(
                    (
                        embedder.version + ":split:" + group.key + ":" + ",".join(group.member_ids)
                    ).encode()
                ).hexdigest(),
                "ambiguous_matches": (group.key,),
            }
        )
        if matched_keys.count(group.key) > 1
        else group
        for group in result
    )

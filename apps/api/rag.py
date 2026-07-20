"""RAG embeddings. Two embedders behind one interface:

- HashEmbedder — deterministic bag-of-words feature hashing. Zero deps, zero
  downloads; the CI/default embedder. Surprisingly serviceable for keyword-y
  career/JD text.
- FastEmbedEmbedder — bge-small via fastembed (optional install, ~100 MB CPU
  model; the heaviest thing allowed under the lightweight rule). Enabled with
  CAREERPILOT_EMBEDDER=fastembed once `pip install fastembed` has run.
"""
import hashlib
import math
import os
import re

DIM = 256


class HashEmbedder:
    name = "hash-bow-256"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * DIM
            for tok in re.findall(r"[a-z0-9.#+]+", text.lower()):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                vec[h % DIM] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class FastEmbedEmbedder:
    name = "bge-small-en-v1.5"

    def __init__(self):
        from fastembed import TextEmbedding  # lazy: optional dependency
        self._model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model.embed(texts)]


_active = None


def get_embedder():
    global _active
    if _active is None:
        if os.environ.get("CAREERPILOT_EMBEDDER", "hash") == "fastembed":
            _active = FastEmbedEmbedder()
        else:
            _active = HashEmbedder()
    return _active


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)

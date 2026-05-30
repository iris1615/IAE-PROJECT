from typing import List

from sentence_transformers import SentenceTransformer

EMBED_MODEL = "all-MiniLM-L6-v2"

_model_cache: dict[str, SentenceTransformer] = {}


def _get_model(model_name: str = EMBED_MODEL) -> SentenceTransformer:
    model = _model_cache.get(model_name)
    if model is None:
        model = SentenceTransformer(model_name)
        _model_cache[model_name] = model
    return model


def embed_texts(texts: List[str], model_name: str = EMBED_MODEL) -> List[List[float]]:
    model = _get_model(model_name)
    return model.encode(texts, convert_to_numpy=True).tolist()
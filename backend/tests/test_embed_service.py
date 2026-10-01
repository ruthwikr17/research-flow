import numpy as np

from app.services.embed_service import EmbedService


class FakeModel:
    def embed(self, texts):
        vectors = []
        for text in texts:
            vectors.append(np.array([1.0, 0.0]) if "cat" in text.lower() else np.array([0.0, 1.0]))
        return vectors


def test_similarity_prefers_related_chunk(monkeypatch):
    monkeypatch.setattr("app.services.embed_service.TextEmbedding", lambda model_name="BAAI/bge-small-en-v1.5": FakeModel())
    service = EmbedService()
    index, related_score = service.most_similar_chunk("Cats are domestic animals.", ["A cat is a domesticated mammal.", "Volcanoes erupt molten rock."])
    _, unrelated_score = service.most_similar_chunk("Cats are domestic animals.", ["Volcanoes erupt molten rock."])
    assert index == 0
    assert related_score > unrelated_score

import os
from eval.metrics import (
    compute_citation_precision,
    compute_completeness,
    compute_latency_stats,
    compute_verifier_catch_rate,
)


class DummyEmbedService:
    def embed(self, texts):
        # Deterministic mock vectors based on text matching
        res = []
        for text in texts:
            if "RAG" in text or "grounding" in text:
                res.append([1.0, 0.0, 0.0])
            elif "microservice" in text:
                res.append([0.0, 1.0, 0.0])
            else:
                res.append([0.0, 0.0, 1.0])
        return res


def test_compute_citation_precision():
    claims = [
        {"correct": True},
        {"correct": True},
        {"correct": False},
        {"correct": True},
    ]
    precision = compute_citation_precision(claims)
    assert precision == 75.0


def test_compute_completeness():
    embed_service = DummyEmbedService()
    angles = ["RAG and grounding", "microservice architecture"]
    report = "This report discusses RAG and grounding techniques in detail.\nIt also covers microservice deployment."
    completeness = compute_completeness(report, angles, embed_service, threshold=0.5)
    assert completeness == 100.0


def test_compute_latency_stats():
    timings = [
        {"total": 10.0, "planning": 1.0, "researching": 5.0, "synthesizing": 2.0, "verifying": 2.0},
        {"total": 20.0, "planning": 2.0, "researching": 10.0, "synthesizing": 4.0, "verifying": 4.0},
    ]
    stats = compute_latency_stats(timings)
    assert stats["mean_total"] == 15.0
    assert stats["median_total"] == 15.0
    assert stats["p95_total"] == 20.0
    assert stats["mean_planning"] == 1.5


def test_compute_verifier_catch_rate():
    preds = ["unsupported", "supported", "partially_supported", "unsupported"]
    ground_truth = ["unsupported", "supported", "partially_supported", "supported"]

    res = compute_verifier_catch_rate(preds, ground_truth)
    assert res["verifier_precision"] == 0.5  # 1 TP, 1 FP (pred unsupported for GT supported)
    assert res["verifier_recall"] == 1.0     # 1 TP out of 1 GT unsupported
    assert "confusion_matrix" in res

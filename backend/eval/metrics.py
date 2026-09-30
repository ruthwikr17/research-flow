from __future__ import annotations

import statistics
from typing import Any
import numpy as np


def compute_citation_precision(scored_claims: list[dict[str, Any]]) -> float:
    """Computes percentage of claims manually marked as correctly cited."""
    if not scored_claims:
        return 0.0
    correct = sum(1 for c in scored_claims if c.get("correct", False))
    return round((correct / len(scored_claims)) * 100, 2)


def compute_completeness(report_text: str, expected_angles: list[str], embed_service: Any, threshold: float = 0.5) -> float:
    """Computes expected angle coverage by cosine similarity of embeddings."""
    if not expected_angles or not report_text.strip():
        return 0.0

    angle_embeds = embed_service.embed(expected_angles)
    report_lines = [line.strip() for line in report_text.split("\n") if line.strip()]
    if not report_lines:
        return 0.0

    line_embeds = embed_service.embed(report_lines)
    line_vectors = [np.asarray(v) for v in line_embeds]

    covered_count = 0
    for angle_emb in angle_embeds:
        angle_vec = np.asarray(angle_emb)
        best_sim = max(float(np.dot(angle_vec, l_vec)) for l_vec in line_vectors)
        if best_sim >= threshold:
            covered_count += 1

    return round((covered_count / len(expected_angles)) * 100, 2)


def compute_latency_stats(timings: list[dict[str, float]]) -> dict[str, float]:
    """Computes total & per-stage latency metrics (mean, median, p95)."""
    if not timings:
        return {}

    totals = [t.get("total", 0.0) for t in timings]
    totals_sorted = sorted(totals)
    n = len(totals_sorted)

    median_idx = n // 2
    median_val = totals_sorted[median_idx] if n % 2 != 0 else (totals_sorted[median_idx - 1] + totals_sorted[median_idx]) / 2.0
    p95_idx = int(n * 0.95)

    res = {
        "mean_total": round(statistics.mean(totals), 2),
        "median_total": round(median_val, 2),
        "p95_total": round(totals_sorted[min(p95_idx, n - 1)], 2),
    }

    for stage in ["planning", "researching", "synthesizing", "verifying"]:
        stage_times = [t.get(stage, 0.0) for t in timings]
        if stage_times:
            res[f"mean_{stage}"] = round(statistics.mean(stage_times), 2)

    return res


def compute_verifier_catch_rate(predictions: list[str], ground_truth: list[str]) -> dict[str, Any]:
    """Computes verifier precision, recall, F1 (unsupported class as positive), and 3x3 confusion matrix."""
    verdict_labels = ["supported", "partially_supported", "unsupported"]
    matrix = {row: {col: 0 for col in verdict_labels} for row in verdict_labels}

    for pred, gt in zip(predictions, ground_truth, strict=True):
        if pred in matrix and gt in matrix:
            matrix[gt][pred] += 1

    # Catch rate: "unsupported" treated as positive class
    tp = matrix["unsupported"]["unsupported"]
    fp = matrix["supported"]["unsupported"] + matrix["partially_supported"]["unsupported"]
    fn = matrix["unsupported"]["supported"] + matrix["unsupported"]["partially_supported"]

    precision = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
    recall = round(tp / (tp + fn), 4) if (tp + fn) > 0 else 0.0
    f1 = round((2 * precision * recall) / (precision + recall), 4) if (precision + recall) > 0 else 0.0

    return {
        "verifier_precision": precision,
        "verifier_recall": recall,
        "verifier_f1": f1,
        "confusion_matrix": matrix,
    }

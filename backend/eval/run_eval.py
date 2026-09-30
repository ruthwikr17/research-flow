from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from app.agents.prompts.verifier_prompt import VERIFIER_SYSTEM_PROMPT
from app.agents.verifier import VerifierAgent, VerifierOutput
from app.config import get_settings
from app.services.embed_service import EmbedService
from app.services.llm_router import LLMRouter, SDKAdapter
from app.services.orchestrator import ResearchOrchestrator
from app.agents.planner import PlannerAgent
from app.agents.researcher import ResearcherAgent
from app.agents.synthesizer import SynthesizerAgent
from app.services.quota_monitor import QuotaMonitor
from app.services.search_service import SearchService
from eval.metrics import (
    compute_citation_precision,
    compute_completeness,
    compute_latency_stats,
    compute_verifier_catch_rate,
)

EVAL_DIR = Path(__file__).parent
DATASET_DIR = EVAL_DIR / "dataset"
RESULTS_DIR = EVAL_DIR / "results"


def init_backend_services():
    settings = get_settings()
    quota_monitor = QuotaMonitor(settings.gemini_project_keys)
    llm_router = LLMRouter(quota_monitor, SDKAdapter(settings.groq_api_key))
    search_service = SearchService(
        settings.tavily_api_key,
        settings.exa_api_key,
        settings.tavily_monthly_credit_limit,
        settings.exa_monthly_credit_budget,
    )
    embed_service = EmbedService()
    verifier = VerifierAgent(llm_router, embed_service)
    orchestrator = ResearchOrchestrator(
        PlannerAgent(llm_router),
        lambda: ResearcherAgent(llm_router, search_service, max_searches=settings.max_searches_per_researcher),
        SynthesizerAgent(llm_router),
        verifier,
        max_concurrent_researchers=settings.max_concurrent_researchers,
        timeout_seconds=settings.pipeline_timeout_seconds,
    )
    return orchestrator, verifier, embed_service, llm_router


async def run_track_1(orchestrator: ResearchOrchestrator, embed_service: EmbedService, max_queries: int | None = None):
    """Full-pipeline eval track."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATASET_DIR / "test_queries.json") as f:
        queries = json.load(f)

    if max_queries:
        queries = queries[:max_queries]

    pipeline_results = []
    timings_list = []
    completeness_scores = []
    scoring_template_lines = [
        "# Human Scoring Template for Citation Precision",
        "",
        "Instructions: Mark `[x] correct` if the cited source and audit chunk support the claim text, or `[x] incorrect` if not.",
        "",
    ]

    print(f"\n--- Track 1: Running Full Pipeline ({len(queries)} queries) ---")
    for item in queries:
        qid = item["id"]
        query_text = item["query"]
        expected_angles = item.get("expected_angles", [])
        print(f"Executing [{qid}]: {query_text}")

        report = await orchestrator.run_pipeline(query_text)
        report_dict = report.model_dump() if hasattr(report, "model_dump") else dict(report)
        pipeline_results.append(report_dict)

        if hasattr(report, "timings") and report.timings:
            timings_list.append(report.timings)

        # Compute completeness for this query
        report_text = f"{report.intro}\n" + "\n".join(
            f"{s.title}\n" + "\n".join(c.text for c in s.claims) for s in report.sections
        ) + f"\n{report.conclusion}"
        comp = compute_completeness(report_text, expected_angles, embed_service)
        completeness_scores.append(comp)

        # Build scoring template lines for surviving claims
        scoring_template_lines.append(f"## Query [{qid}]: {query_text}")
        for section in report.sections:
            scoring_template_lines.append(f"### Section: {section.title}")
            for claim in section.claims:
                verdict = claim.verdict
                audit_chunk = verdict.audit_chunk_text if verdict else ""
                source_urls = ", ".join(claim.supporting_source_urls)
                scoring_template_lines.extend([
                    f"- **Claim [{claim.id}]**: {claim.text}",
                    f"  - **Sources**: {source_urls}",
                    f"  - **Audit Chunk**: {audit_chunk}",
                    "  - [ ] correct   [ ] incorrect",
                    "",
                ])

    with open(RESULTS_DIR / "pipeline_runs.json", "w") as f:
        json.dump(pipeline_results, f, indent=2)

    with open(RESULTS_DIR / "citation_scoring_template.md", "w") as f:
        f.write("\n".join(scoring_template_lines))

    avg_completeness = round(sum(completeness_scores) / len(completeness_scores), 2) if completeness_scores else 0.0
    latency_stats = compute_latency_stats(timings_list)

    return {
        "completeness_avg": avg_completeness,
        "latency_stats": latency_stats,
    }


def run_track_2(verifier: VerifierAgent, max_samples: int | None = None):
    """Verifier-isolated eval track."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATASET_DIR / "verifier_test_set.json") as f:
        test_set = json.load(f)

    if max_samples:
        test_set = test_set[:max_samples]

    print(f"\n--- Track 2: Running Verifier-Isolated Eval ({len(test_set)} samples) ---")
    predictions = []
    ground_truths = []
    results = []

    for item in test_set:
        vid = item["id"]
        claim_text = item["claim"]
        chunk_text = item["chunk_text"]
        gt_verdict = item["ground_truth_verdict"]

        print(f"Verifying [{vid}]...")
        # Call Verifier structured call directly without search/retrieval
        output: VerifierOutput = verifier.call_structured(
            "verifier",
            [
                {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": f"Claim: {claim_text}\n\nSource excerpt:\n{chunk_text}"},
            ],
            VerifierOutput,
            exclude_provider=None,
        )

        pred_verdict = output.verdict
        predictions.append(pred_verdict)
        ground_truths.append(gt_verdict)

        results.append({
            "id": vid,
            "claim": claim_text,
            "chunk_text": chunk_text,
            "ground_truth": gt_verdict,
            "predicted": pred_verdict,
            "confidence": output.confidence,
            "reasoning": output.reasoning,
        })

    with open(RESULTS_DIR / "verifier_eval_results.json", "w") as f:
        json.dump(results, f, indent=2)

    catch_rate_metrics = compute_verifier_catch_rate(predictions, ground_truths)
    return catch_rate_metrics


def generate_summary_report(t1_res: dict[str, Any] | None, t2_res: dict[str, Any] | None, citation_precision: float | None = None):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    cit_prec_str = f"{citation_precision}%" if citation_precision is not None else "Pending human scoring"
    comp_str = f"{t1_res['completeness_avg']}%" if t1_res else "N/A"
    med_lat = f"{t1_res['latency_stats'].get('median_total', 'N/A')}s" if t1_res and "latency_stats" in t1_res else "N/A"
    p95_lat = f"{t1_res['latency_stats'].get('p95_total', 'N/A')}s" if t1_res and "latency_stats" in t1_res else "N/A"

    f1_str = f"{t2_res['verifier_f1']}" if t2_res else "N/A"
    prec_str = f"{t2_res['verifier_precision']}" if t2_res else "N/A"
    rec_str = f"{t2_res['verifier_recall']}" if t2_res else "N/A"

    markdown_table = f"""# ResearchFlow Evaluation Summary

| Metric                    | Value |
|---------------------------|-------|
| Citation precision        | {cit_prec_str}   |
| Completeness (avg)        | {comp_str}   |
| Latency (median, total)   | {med_lat}   |
| Latency (p95, total)      | {p95_lat}   |
| Verifier catch rate (F1)  | {f1_str}  |
| Verifier precision        | {prec_str}  |
| Verifier recall           | {rec_str}  |
"""

    with open(RESULTS_DIR / "summary.md", "w") as f:
        f.write(markdown_table)

    print("\n================ SUMMARY RESULTS ================")
    print(markdown_table)


def main():
    parser = argparse.ArgumentParser(description="ResearchFlow Evaluation Harness")
    parser.add_argument("--track", choices=["1", "2", "all"], default="all", help="Which eval track to run")
    parser.add_argument("--max-queries", type=int, default=None, help="Limit full-pipeline queries for quick runs")
    parser.add_argument("--score-citation-file", type=str, default=None, help="Path to scored citation template markdown file")
    args = parser.parse_args()

    if args.score_citation_file:
        scored_path = Path(args.score_citation_file)
        if not scored_path.exists():
            print(f"Error: {scored_path} does not exist.")
            return
        content = scored_path.read_text()
        claims = []
        for line in content.split("\n"):
            if "[x] correct" in line.lower():
                claims.append({"correct": True})
            elif "[x] incorrect" in line.lower():
                claims.append({"correct": False})
        prec = compute_citation_precision(claims)
        print(f"Computed Citation Precision from {scored_path}: {prec}% ({sum(1 for c in claims if c['correct'])}/{len(claims)})")
        return

    orchestrator, verifier, embed_service, _ = init_backend_services()

    t1_res = None
    t2_res = None

    if args.track in ["1", "all"]:
        t1_res = asyncio.run(run_track_1(orchestrator, embed_service, max_queries=args.max_queries))

    if args.track in ["2", "all"]:
        t2_res = run_track_2(verifier, max_samples=args.max_queries)

    generate_summary_report(t1_res, t2_res)


if __name__ == "__main__":
    main()

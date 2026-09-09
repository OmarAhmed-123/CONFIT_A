"""
Visual Search Quality Gate Benchmark

Runs comprehensive evaluation including:
- Baseline vs Enhanced metrics
- Regression analysis
- Synonym validation
- Color analysis
- Score distribution
- Weight sensitivity
- Overfitting controls (train/holdout split)
- Determinism verification
- Performance measurement
"""

import json
import time
import math
import statistics
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict

from backend.app.services.visual_search_enhanced import (
    calculate_enhanced_score,
    normalize_synonym,
    get_category_match_level,
    get_color_similarity,
    get_style_similarity,
    WEIGHTS,
)


def load_dataset(path: str) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def baseline_score(detected_category, detected_color, detected_style, detected_pattern,
                   product_category, product_color, product_style_tags, product_title,
                   analysis_available) -> Tuple[float, Dict]:
    """Baseline scoring algorithm (token-matching)."""
    cat_tokens = [t for t in (detected_category or "").lower().replace("&", " ").split() if len(t) > 2]
    col_tokens = [t for t in (detected_color or "").lower().split() if len(t) > 2]
    sty_tokens = [t.replace(" ", "_") for t in (detected_style or "").lower().split("/") if t.strip()]

    score = 50.0
    cat_matched = False
    col_matched = False
    sty_matched = False

    if analysis_available:
        if any(t in product_category.lower() or t in product_title.lower() for t in cat_tokens):
            score += 30.0
            cat_matched = True
        if any(t in product_color.lower() for t in col_tokens):
            score += 15.0
            col_matched = True
        if any(t in product_style_tags.lower() for t in sty_tokens):
            score += 8.0
            sty_matched = True

    score = min(98.0, round(score, 1))
    return score, {"base": 50.0, "category": 30.0 if cat_matched else 0.0,
                    "color": 15.0 if col_matched else 0.0, "style": 8.0 if sty_matched else 0.0}


def dcg(relevances: List[float]) -> float:
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances))


def ndcg_at_k(ranked_relevances: List[float], k: int) -> float:
    dcg_val = dcg(ranked_relevances[:k])
    ideal = sorted(ranked_relevances, reverse=True)
    idcg_val = dcg(ideal[:k])
    return dcg_val / idcg_val if idcg_val > 0 else 0.0


def precision_at_k(ranked_relevances: List[float], k: int, threshold: float = 1.0) -> float:
    return sum(1 for r in ranked_relevances[:k] if r >= threshold) / k if k > 0 else 0.0


def recall_at_k(ranked_relevances: List[float], k: int, total_relevant: int, threshold: float = 1.0) -> float:
    if total_relevant == 0: return 0.0
    return sum(1 for r in ranked_relevances[:k] if r >= threshold) / total_relevant


def mrr(ranked_relevances: List[float], threshold: float = 2.0) -> float:
    for i, rel in enumerate(ranked_relevances):
        if rel >= threshold: return 1.0 / (i + 1)
    return 0.0


def score_product(catalog, vision, score_fn):
    """Score all products and return sorted list."""
    scored = []
    start = time.perf_counter()
    for pid, pdata in catalog.items():
        score, breakdown = score_fn(pdata, vision)
        scored.append((pid, score, breakdown))
    elapsed = (time.perf_counter() - start) * 1000
    scored.sort(key=lambda x: (-x[1], x[2].get("category", 0), x[2].get("color", 0)))
    return scored, elapsed


def run_single_query(query, catalog, score_fn):
    """Run a single query and return metrics."""
    vision = query["vision_output"]
    gt = query["ground_truth"]

    scored, elapsed = score_product(catalog, vision, score_fn)
    ranked_pids = [s[0] for s in scored]
    ranked_relevances = [float(gt.get(pid, 0)) for pid in ranked_pids]
    total_relevant = sum(1 for v in gt.values() if v >= 1)

    return {
        "query_id": query["id"],
        "top5_products": ranked_pids[:5],
        "top5_scores": [s[1] for s in scored[:5]],
        "top5_relevances": ranked_relevances[:5],
        "ranked_products": ranked_pids,
        "ranked_scores": [s[1] for s in scored],
        "ranked_relevances": ranked_relevances,
        "ndcg@5": ndcg_at_k(ranked_relevances, 5),
        "ndcg@10": ndcg_at_k(ranked_relevances, 10),
        "precision@5": precision_at_k(ranked_relevances, 5),
        "precision@10": precision_at_k(ranked_relevances, 10),
        "recall@5": recall_at_k(ranked_relevances, 5, total_relevant),
        "recall@10": recall_at_k(ranked_relevances, 10, total_relevant),
        "mrr": mrr(ranked_relevances),
        "latency_ms": elapsed,
        "all_scores": [(s[0], s[1]) for s in scored],
    }


def aggregate_metrics(query_results: List[Dict]) -> Dict:
    """Aggregate metrics across queries."""
    return {
        "n_queries": len(query_results),
        "ndcg@5_mean": statistics.mean(q["ndcg@5"] for q in query_results),
        "ndcg@10_mean": statistics.mean(q["ndcg@10"] for q in query_results),
        "precision@5_mean": statistics.mean(q["precision@5"] for q in query_results),
        "precision@10_mean": statistics.mean(q["precision@10"] for q in query_results),
        "recall@5_mean": statistics.mean(q["recall@5"] for q in query_results),
        "recall@10_mean": statistics.mean(q["recall@10"] for q in query_results),
        "mrr_mean": statistics.mean(q["mrr"] for q in query_results),
        "latency_ms_mean": statistics.mean(q["latency_ms"] for q in query_results),
        "latency_ms_median": statistics.median(q["latency_ms"] for q in query_results),
        "latency_ms_p95": sorted(q["latency_ms"] for q in query_results)[int(0.95 * len(query_results))],
    }


def run_weight_sensitivity(catalog, queries, query_fn):
    """Test different weight configurations."""
    configs = {
        "current": {"category_match": 35, "color_match": 20, "style_match": 10, "pattern_match": 5, "base_score": 20},
        "category_dominant": {"category_match": 45, "color_match": 15, "style_match": 8, "pattern_match": 3, "base_score": 15},
        "balanced": {"category_match": 25, "color_match": 20, "style_match": 15, "pattern_match": 5, "base_score": 20},
        "color_dominant": {"category_match": 25, "color_match": 30, "style_match": 10, "pattern_match": 5, "base_score": 15},
        "conservative": {"category_match": 30, "color_match": 15, "style_match": 5, "pattern_match": 3, "base_score": 25},
        "aggressive": {"category_match": 40, "color_match": 25, "style_match": 15, "pattern_match": 5, "base_score": 10},
    }

    results = {}
    original_weights = WEIGHTS.copy()

    for name, weights in configs.items():
        WEIGHTS.update(weights)
        qr = []
        for query in queries:
            qr.append(query_fn(query))
        agg = aggregate_metrics(qr)
        results[name] = {
            "ndcg@5": agg["ndcg@5_mean"],
            "ndcg@10": agg["ndcg@10_mean"],
            "precision@5": agg["precision@5_mean"],
            "mrr": agg["mrr_mean"],
        }

    WEIGHTS.update(original_weights)
    return results


def main():
    dataset_path = Path(__file__).parent.parent.parent / "docs" / "visual-search-evaluation" / "evaluation-dataset-v3.json"
    if not dataset_path.exists():
        print(f"ERROR: Dataset not found at {dataset_path}")
        return

    dataset = load_dataset(str(dataset_path))
    catalog = dataset["product_catalog"]
    all_queries = dataset["evaluation_queries"]
    original_ids = set(dataset.get("subset_original", []))

    # Split: original 20 as holdout, rest as development
    dev_queries = [q for q in all_queries if q["id"] not in original_ids]
    holdout_queries = [q for q in all_queries if q["id"] in original_ids]

    print("=" * 80)
    print("CONFIT_A VISUAL SEARCH QUALITY GATE BENCHMARK")
    print("=" * 80)
    print(f"\nDataset: {dataset_path}")
    print(f"Total queries: {len(all_queries)}")
    print(f"Development set: {len(dev_queries)}")
    print(f"Holdout set: {len(holdout_queries)}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    # === BASELINE vs ENHANCED (FULL DATASET) ===
    print("\n" + "=" * 80)
    print("FULL DATASET: BASELINE vs ENHANCED")
    print("=" * 80)

    baseline_fn = lambda p, v: baseline_score(
        v.get("detected_category"), v.get("detected_color"), v.get("detected_style"),
        v.get("detected_pattern"), p.get("category",""), p.get("color_family",""),
        p.get("style_tags",""), p.get("title",""), v.get("analysis_available", False))
    enhanced_fn = lambda p, v: calculate_enhanced_score(
        v.get("detected_category"), v.get("detected_color"), v.get("detected_style"),
        v.get("detected_pattern"), p.get("category",""), p.get("color_family",""),
        p.get("style_tags",""), p.get("title",""), v.get("analysis_available", False))

    baseline_results = [run_single_query(q, catalog, baseline_fn) for q in all_queries]
    enhanced_results = [run_single_query(q, catalog, enhanced_fn) for q in all_queries]

    b_agg = aggregate_metrics(baseline_results)
    e_agg = aggregate_metrics(enhanced_results)

    print(f"\n{'Metric':<30} {'Baseline':>12} {'Enhanced':>12} {'Delta':>12} {'Rel%':>10}")
    print("-" * 80)
    for metric in ["ndcg@5_mean", "ndcg@10_mean", "precision@5_mean", "precision@10_mean",
                    "recall@5_mean", "recall@10_mean", "mrr_mean"]:
        b = b_agg[metric]
        e = e_agg[metric]
        d = e - b
        r = d / b * 100 if b != 0 else 0
        print(f"{metric:<30} {b:>12.4f} {e:>12.4f} {d:>+12.4f} {r:>+9.1f}%")

    # === HOLDOUT VALIDATION ===
    print("\n" + "=" * 80)
    print("HOLDOUT VALIDATION (Original 20 queries)")
    print("=" * 80)

    b_holdout = [run_single_query(q, catalog, baseline_fn) for q in holdout_queries]
    e_holdout = [run_single_query(q, catalog, enhanced_fn) for q in holdout_queries]
    b_ho_agg = aggregate_metrics(b_holdout)
    e_ho_agg = aggregate_metrics(e_holdout)

    print(f"\n{'Metric':<30} {'Baseline':>12} {'Enhanced':>12} {'Delta':>12} {'Rel%':>10}")
    print("-" * 80)
    for metric in ["ndcg@5_mean", "ndcg@10_mean", "precision@5_mean", "precision@10_mean",
                    "recall@5_mean", "recall@10_mean", "mrr_mean"]:
        b = b_ho_agg[metric]
        e = e_ho_agg[metric]
        d = e - b
        r = d / b * 100 if b != 0 else 0
        print(f"{metric:<30} {b:>12.4f} {e:>12.4f} {d:>+12.4f} {r:>+9.1f}%")

    # === REGRESSION ANALYSIS ===
    print("\n" + "=" * 80)
    print("REGRESSION ANALYSIS")
    print("=" * 80)

    regressions = []
    for bq, eq in zip(baseline_results, enhanced_results):
        if bq["ndcg@5"] > eq["ndcg@5"] + 0.01:  # meaningful regression
            regressions.append({
                "query_id": bq["query_id"],
                "baseline_ndcg5": bq["ndcg@5"],
                "enhanced_ndcg5": eq["ndcg@5"],
                "delta": eq["ndcg@5"] - bq["ndcg@5"],
                "baseline_top3": bq["top5_products"][:3],
                "enhanced_top3": eq["top5_products"][:3],
            })

    print(f"\nRegressions found: {len(regressions)}")
    if regressions:
        print(f"\n{'Query':<10} {'Baseline':>10} {'Enhanced':>10} {'Delta':>10} {'Root Cause'}")
        print("-" * 80)
        for r in regressions[:20]:
            print(f"{r['query_id']:<10} {r['baseline_ndcg5']:>10.3f} {r['enhanced_ndcg5']:>10.3f} {r['delta']:>+10.3f}")

    improvements = []
    for bq, eq in zip(baseline_results, enhanced_results):
        if eq["ndcg@5"] > bq["ndcg@5"] + 0.01:
            improvements.append({
                "query_id": bq["query_id"],
                "baseline_ndcg5": bq["ndcg@5"],
                "enhanced_ndcg5": eq["ndcg@5"],
                "delta": eq["ndcg@5"] - bq["ndcg@5"],
            })

    print(f"\nImprovements found: {len(improvements)}")
    if improvements:
        print(f"\n{'Query':<10} {'Baseline':>10} {'Enhanced':>10} {'Delta':>10}")
        print("-" * 50)
        for r in improvements[:20]:
            print(f"{r['query_id']:<10} {r['baseline_ndcg5']:>10.3f} {r['enhanced_ndcg5']:>10.3f} {r['delta']:>+10.3f}")

    # === SYNONYM ANALYSIS ===
    print("\n" + "=" * 80)
    print("SYNONYM ANALYSIS")
    print("=" * 80)

    synonym_queries = [q for q in all_queries if "SYNONYM" in q.get("notes", "")]
    b_syn = [run_single_query(q, catalog, baseline_fn) for q in synonym_queries]
    e_syn = [run_single_query(q, catalog, enhanced_fn) for q in synonym_queries]

    b_syn_top1 = sum(1 for q in b_syn if q["top5_products"] and q["top5_relevances"][0] >= 2.0)
    e_syn_top1 = sum(1 for q in e_syn if q["top5_products"] and q["top5_relevances"][0] >= 2.0)
    b_syn_top5 = sum(1 for q in b_syn if any(r >= 2.0 for r in q["top5_relevances"][:5]))
    e_syn_top5 = sum(1 for q in e_syn if any(r >= 2.0 for r in q["top5_relevances"][:5]))

    print(f"\nSynonym queries: {len(synonym_queries)}")
    print(f"{'Metric':<30} {'Baseline':>12} {'Enhanced':>12}")
    print("-" * 60)
    print(f"{'Top-1 success':<30} {b_syn_top1:>12} {e_syn_top1:>12}")
    print(f"{'Top-5 success':<30} {b_syn_top5:>12} {e_syn_top5:>12}")
    print(f"{'nDCG@5 mean':<30} {statistics.mean(q['ndcg@5'] for q in b_syn):>12.4f} {statistics.mean(q['ndcg@5'] for q in e_syn):>12.4f}")

    # === COLOR ANALYSIS ===
    print("\n" + "=" * 80)
    print("COLOR ANALYSIS")
    print("=" * 80)

    color_cases = {
        "exact_same": [("EQ13","green","green"), ("EQ56","dark blue","blue")],
        "same_family": [("EQ56","dark blue","navy"), ("EQ57","navy","blue")],
        "adjacent": [("EQ04","dark blue","navy"), ("EQ60","burgundy","red")],
        "different": [("EQ05","red","black"), ("EQ14","black","white")],
    }

    for case_type, cases in color_cases.items():
        b_scores = []
        e_scores = []
        for qid, c1, c2 in cases:
            sim = get_color_similarity(c1, c2)
            # Find the query
            query = next((q for q in all_queries if q["id"] == qid), None)
            if query:
                b_result = run_single_query(query, catalog, baseline_fn)
                e_result = run_single_query(query, catalog, enhanced_fn)
                b_scores.append(b_result["ndcg@5"])
                e_scores.append(e_result["ndcg@5"])

        if b_scores:
            print(f"\n{case_type}: color_sim={get_color_similarity(c1,c2):.2f}")
            print(f"  Baseline nDCG@5: {statistics.mean(b_scores):.3f}")
            print(f"  Enhanced nDCG@5: {statistics.mean(e_scores):.3f}")

    # === SCORE DISTRIBUTION ===
    print("\n" + "=" * 80)
    print("SCORE DISTRIBUTION (All queries, all products)")
    print("=" * 80)

    all_b_scores = []
    all_e_scores = []
    for query in all_queries:
        vision = query["vision_output"]
        for pid, pdata in catalog.items():
            bs, _ = baseline_fn(pdata, vision)
            es, _ = enhanced_fn(pdata, vision)
            all_b_scores.append(bs)
            all_e_scores.append(es)

    for name, scores in [("Baseline", all_b_scores), ("Enhanced", all_e_scores)]:
        print(f"\n{name}:")
        print(f"  Min: {min(scores):.1f}")
        print(f"  Max: {max(scores):.1f}")
        print(f"  Mean: {statistics.mean(scores):.1f}")
        print(f"  Median: {statistics.median(scores):.1f}")
        print(f"  At 98: {sum(1 for s in scores if s >= 98)} ({sum(1 for s in scores if s >= 98)/len(scores)*100:.1f}%)")
        print(f"  At 95+: {sum(1 for s in scores if s >= 95)} ({sum(1 for s in scores if s >= 95)/len(scores)*100:.1f}%)")

    # === WEIGHT SENSITIVITY ===
    print("\n" + "=" * 80)
    print("WEIGHT SENSITIVITY (Development set only)")
    print("=" * 80)

    ws_fn = lambda q: run_single_query(q, catalog, enhanced_fn)
    weight_results = run_weight_sensitivity(catalog, dev_queries, ws_fn)

    print(f"\n{'Config':<25} {'nDCG@5':>10} {'nDCG@10':>10} {'P@5':>10} {'MRR':>10}")
    print("-" * 70)
    for name, metrics in weight_results.items():
        print(f"{name:<25} {metrics['ndcg@5']:>10.4f} {metrics['ndcg@10']:>10.4f} {metrics['precision@5']:>10.4f} {metrics['mrr']:>10.4f}")

    # === DETERMINISM ===
    print("\n" + "=" * 80)
    print("DETERMINISM VERIFICATION")
    print("=" * 80)

    test_query = all_queries[0]
    results_runs = []
    for _ in range(5):
        result = run_single_query(test_query, catalog, enhanced_fn)
        results_runs.append(result["top5_products"])

    all_same = all(r == results_runs[0] for r in results_runs)
    print(f"\n5 runs of same query: {'DETERMINISTIC ✓' if all_same else 'NON-DETERMINISTIC ✗'}")
    if not all_same:
        for i, r in enumerate(results_runs):
            print(f"  Run {i}: {r}")

    # === PERFORMANCE ===
    print("\n" + "=" * 80)
    print("PERFORMANCE")
    print("=" * 80)

    b_latencies = [q["latency_ms"] for q in baseline_results]
    e_latencies = [q["latency_ms"] for q in enhanced_results]

    print(f"\n{'Metric':<20} {'Baseline':>12} {'Enhanced':>12} {'Samples':>10}")
    print("-" * 60)
    print(f"{'Mean (ms)':<20} {statistics.mean(b_latencies):>12.3f} {statistics.mean(e_latencies):>12.3f} {len(all_queries):>10}")
    print(f"{'Median (ms)':<20} {statistics.median(b_latencies):>12.3f} {statistics.median(e_latencies):>12.3f}")
    print(f"{'P95 (ms)':<20} {sorted(b_latencies)[int(0.95*len(b_latencies))]:>12.3f} {sorted(e_latencies)[int(0.95*len(e_latencies))]:>12.3f}")

    # === SAVE RESULTS ===
    output = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "dataset": str(dataset_path),
        "total_queries": len(all_queries),
        "dev_queries": len(dev_queries),
        "holdout_queries": len(holdout_queries),
        "full_dataset": {"baseline": b_agg, "enhanced": e_agg},
        "holdout": {"baseline": b_ho_agg, "enhanced": e_ho_agg},
        "regressions": regressions,
        "improvements": improvements,
        "synonym_analysis": {
            "total": len(synonym_queries),
            "baseline_top1": b_syn_top1,
            "enhanced_top1": e_syn_top1,
            "baseline_top5": b_syn_top5,
            "enhanced_top5": e_syn_top5,
        },
        "weight_sensitivity": weight_results,
        "determinism": all_same,
        "score_distribution": {
            "baseline": {"min": min(all_b_scores), "max": max(all_b_scores),
                        "mean": statistics.mean(all_b_scores), "median": statistics.median(all_b_scores),
                        "at_98": sum(1 for s in all_b_scores if s >= 98)},
            "enhanced": {"min": min(all_e_scores), "max": max(all_e_scores),
                        "mean": statistics.mean(all_e_scores), "median": statistics.median(all_e_scores),
                        "at_98": sum(1 for s in all_e_scores if s >= 98)},
        },
    }

    output_path = Path(__file__).parent.parent.parent / "docs" / "visual-search-evaluation" / "quality-gate-results.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()

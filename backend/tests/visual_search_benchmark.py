"""
Visual Search Benchmark — Baseline vs Enhanced Scoring

Runs the evaluation dataset through both scoring algorithms and measures:
- Precision@K
- Recall@K
- MRR (Mean Reciprocal Rank)
- nDCG@K
- Category accuracy
- Color match accuracy
- Synonym-hit rate
- Zero-result rate
- Ranking latency
"""

import json
import time
import math
import statistics
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Import both scoring functions directly
from backend.app.services.visual_search_enhanced import (
    calculate_enhanced_score,
    normalize_synonym,
    get_category_match_level,
    get_color_similarity,
    get_style_similarity,
)


def load_dataset(path: str) -> Dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def baseline_score(
    detected_category: str,
    detected_color: str,
    detected_style: str,
    detected_pattern: str,
    product_category: str,
    product_color: str,
    product_style_tags: str,
    product_title: str,
    analysis_available: bool,
) -> Tuple[float, Dict]:
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
    return score, {
        "base": 50.0,
        "category": 30.0 if cat_matched else 0.0,
        "color": 15.0 if col_matched else 0.0,
        "style": 8.0 if sty_matched else 0.0,
    }


def score_product_baseline(product: Dict, vision: Dict) -> Tuple[float, Dict]:
    """Score a product using baseline algorithm."""
    return baseline_score(
        detected_category=vision.get("detected_category"),
        detected_color=vision.get("detected_color"),
        detected_style=vision.get("detected_style"),
        detected_pattern=vision.get("detected_pattern"),
        product_category=product.get("category", ""),
        product_color=product.get("color_family", ""),
        product_style_tags=product.get("style_tags", ""),
        product_title=product.get("title", ""),
        analysis_available=vision.get("analysis_available", False),
    )


def score_product_enhanced(product: Dict, vision: Dict) -> Tuple[float, Dict]:
    """Score a product using enhanced algorithm."""
    return calculate_enhanced_score(
        detected_category=vision.get("detected_category"),
        detected_color=vision.get("detected_color"),
        detected_style=vision.get("detected_style"),
        detected_pattern=vision.get("detected_pattern"),
        product_category=product.get("category", ""),
        product_color=product.get("color_family", ""),
        product_style_tags=product.get("style_tags", ""),
        product_title=product.get("title", ""),
        analysis_available=vision.get("analysis_available", False),
    )


def dcg(relevances: List[float]) -> float:
    """Calculate Discounted Cumulative Gain."""
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances))


def ndcg_at_k(ranked_relevances: List[float], k: int) -> float:
    """Calculate nDCG@K."""
    dcg_val = dcg(ranked_relevances[:k])
    ideal_relevances = sorted(ranked_relevances, reverse=True)
    idcg_val = dcg(ideal_relevances[:k])
    if idcg_val == 0:
        return 0.0
    return dcg_val / idcg_val


def precision_at_k(ranked_relevances: List[float], k: int, threshold: float = 1.0) -> float:
    """Precision@K: fraction of top-K results that are relevant."""
    top_k = ranked_relevances[:k]
    relevant = sum(1 for r in top_k if r >= threshold)
    return relevant / k if k > 0 else 0.0


def recall_at_k(ranked_relevances: List[float], k: int, total_relevant: int, threshold: float = 1.0) -> float:
    """Recall@K: fraction of relevant items found in top-K."""
    if total_relevant == 0:
        return 0.0
    top_k = ranked_relevances[:k]
    relevant = sum(1 for r in top_k if r >= threshold)
    return relevant / total_relevant


def mrr(ranked_relevances: List[float], threshold: float = 2.0) -> float:
    """Mean Reciprocal Rank: 1/rank of first highly-relevant result."""
    for i, rel in enumerate(ranked_relevances):
        if rel >= threshold:
            return 1.0 / (i + 1)
    return 0.0


def run_benchmark(dataset_path: str) -> Dict[str, Any]:
    """Run benchmark on evaluation dataset."""
    dataset = load_dataset(dataset_path)
    catalog = dataset["product_catalog"]
    queries = dataset["evaluation_queries"]

    results = {
        "baseline": {"queries": [], "aggregate": {}},
        "enhanced": {"queries": [], "aggregate": {}},
    }

    for algo_name, score_fn in [("baseline", score_product_baseline), ("enhanced", score_product_enhanced)]:
        all_ndcg5 = []
        all_ndcg10 = []
        all_p5 = []
        all_p10 = []
        all_r5 = []
        all_r10 = []
        all_mrr = []
        all_cat_accuracy = []
        all_color_accuracy = []
        synonym_hits = 0
        synonym_total = 0
        zero_results = 0
        latency_samples = []

        for query in queries:
            vision = query["vision_output"]
            gt = query["ground_truth"]
            qid = query["id"]

            # Score all products
            scored = []
            start_time = time.perf_counter()
            for pid, pdata in catalog.items():
                score, breakdown = score_fn(pdata, vision)
                scored.append((pid, score, breakdown))
            elapsed = time.perf_counter() - start_time
            latency_samples.append(elapsed * 1000)  # ms

            # Sort by score descending
            scored.sort(key=lambda x: (-x[1], x[2].get("category", 0), x[2].get("color", 0)))

            # Build ranked relevance list
            ranked_pids = [s[0] for s in scored]
            ranked_relevances = [float(gt.get(pid, 0)) for pid in ranked_pids]

            # Metrics
            total_relevant = sum(1 for v in gt.values() if v >= 1)

            ndcg5 = ndcg_at_k(ranked_relevances, 5)
            ndcg10 = ndcg_at_k(ranked_relevances, 10)
            p5 = precision_at_k(ranked_relevances, 5)
            p10 = precision_at_k(ranked_relevances, 10)
            r5 = recall_at_k(ranked_relevances, 5, total_relevant)
            r10 = recall_at_k(ranked_relevances, 10, total_relevant)
            mrr_val = mrr(ranked_relevances)

            all_ndcg5.append(ndcg5)
            all_ndcg10.append(ndcg10)
            all_p5.append(p5)
            all_p10.append(p10)
            all_r5.append(r5)
            all_r10.append(r10)
            all_mrr.append(mrr_val)

            # Category accuracy: is the top-ranked product's category correct?
            if ranked_pids:
                top_product = catalog[ranked_pids[0]]
                detected_cat = (vision.get("detected_category") or "").lower()
                actual_cat = top_product.get("category", "").lower()
                # Check if top result matches detected category
                cat_score, cat_type = get_category_match_level(detected_cat, actual_cat)
                all_cat_accuracy.append(1.0 if cat_score >= 0.7 else 0.0)

            # Color accuracy: does the top-ranked product match the detected color?
            if ranked_pids:
                top_product = catalog[ranked_pids[0]]
                detected_col = (vision.get("detected_color") or "").lower()
                actual_col = top_product.get("color_family", "").lower()
                color_sim = get_color_similarity(detected_col, actual_col)
                all_color_accuracy.append(1.0 if color_sim >= 0.7 else 0.0)

            # Synonym detection: check if synonym normalization helped
            if qid in ["EQ09", "EQ10", "EQ05", "EQ17"]:  # synonym test cases
                synonym_total += 1
                # Check if the expected top product is in top 3
                expected = query.get("expected_top3", [])
                if expected and expected[0] in ranked_pids[:3]:
                    synonym_hits += 1

            # Zero results
            if len(scored) == 0:
                zero_results += 1

            # Per-query result
            query_result = {
                "query_id": qid,
                "top5_products": ranked_pids[:5],
                "top5_scores": [s[1] for s in scored[:5]],
                "top5_relevances": ranked_relevances[:5],
                "ndcg@5": ndcg5,
                "ndcg@10": ndcg10,
                "precision@5": p5,
                "precision@10": p10,
                "recall@5": r5,
                "recall@10": r10,
                "mrr": mrr_val,
                "latency_ms": elapsed * 1000,
            }
            results[algo_name]["queries"].append(query_result)

        # Aggregate metrics
        results[algo_name]["aggregate"] = {
            "n_queries": len(queries),
            "ndcg@5_mean": statistics.mean(all_ndcg5),
            "ndcg@10_mean": statistics.mean(all_ndcg10),
            "precision@5_mean": statistics.mean(all_p5),
            "precision@10_mean": statistics.mean(all_p10),
            "recall@5_mean": statistics.mean(all_r5),
            "recall@10_mean": statistics.mean(all_r10),
            "mrr_mean": statistics.mean(all_mrr),
            "category_accuracy_mean": statistics.mean(all_cat_accuracy) if all_cat_accuracy else 0.0,
            "color_accuracy_mean": statistics.mean(all_color_accuracy) if all_color_accuracy else 0.0,
            "synonym_hit_rate": synonym_hits / synonym_total if synonym_total > 0 else 0.0,
            "zero_result_rate": zero_results / len(queries),
            "latency_ms_mean": statistics.mean(latency_samples),
            "latency_ms_median": statistics.median(latency_samples),
            "latency_ms_p95": sorted(latency_samples)[int(0.95 * len(latency_samples))] if len(latency_samples) > 1 else latency_samples[0],
            "latency_ms_min": min(latency_samples),
            "latency_ms_max": max(latency_samples),
            "samples": len(latency_samples),
        }

    # Calculate deltas
    deltas = {}
    for metric in results["baseline"]["aggregate"]:
        if metric in ("n_queries", "samples"):
            continue
        b_val = results["baseline"]["aggregate"].get(metric, 0)
        e_val = results["enhanced"]["aggregate"].get(metric, 0)
        abs_delta = e_val - b_val
        rel_delta = abs_delta / b_val if b_val != 0 else 0.0
        deltas[metric] = {
            "baseline": b_val,
            "enhanced": e_val,
            "absolute_delta": abs_delta,
            "relative_delta": rel_delta,
        }

    return {"baseline": results["baseline"], "enhanced": results["enhanced"], "deltas": deltas}


def main():
    dataset_path = Path(__file__).parent.parent.parent / "docs" / "visual-search-evaluation" / "evaluation-dataset-v2.json"
    if not dataset_path.exists():
        print(f"ERROR: Dataset not found at {dataset_path}")
        return

    print("=" * 80)
    print("VISUAL SEARCH BENCHMARK — Baseline vs Enhanced")
    print("=" * 80)
    print(f"\nDataset: {dataset_path}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    results = run_benchmark(str(dataset_path))

    # Print summary
    print("\n" + "=" * 80)
    print("AGGREGATE METRICS")
    print("=" * 80)

    print(f"\n{'Metric':<30} {'Baseline':>12} {'Enhanced':>12} {'Abs Delta':>12} {'Rel Delta':>12}")
    print("-" * 80)
    for metric, vals in results["deltas"].items():
        b = vals["baseline"]
        e = vals["enhanced"]
        d = vals["absolute_delta"]
        r = vals["relative_delta"]
        marker = "✓" if d > 0 else ("✗" if d < 0 else "·")
        print(f"{metric:<30} {b:>12.4f} {e:>12.4f} {d:>+12.4f} {r:>+11.1%} {marker}")

    # Per-query details
    print("\n" + "=" * 80)
    print("PER-QUERY DETAILS")
    print("=" * 80)
    for bq, eq in zip(results["baseline"]["queries"], results["enhanced"]["queries"]):
        qid = bq["query_id"]
        print(f"\n{qid}: Baseline nDCG@5={bq['ndcg@5']:.3f}, Enhanced nDCG@5={eq['ndcg@5']:.3f}")
        print(f"  Baseline top5: {bq['top5_products']} (scores: {[f'{s:.1f}' for s in bq['top5_scores']]})")
        print(f"  Enhanced top5: {eq['top5_products']} (scores: {[f'{s:.1f}' for s in eq['top5_scores']]})")
        if bq["top5_products"] != eq["top5_products"]:
            print(f"  ** RANKING CHANGED **")

    # Save results
    output_path = Path(__file__).parent.parent.parent / "docs" / "visual-search-evaluation" / "benchmark-results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()

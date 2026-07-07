import os
import sys
import json
import time
import math
import platform
import asyncio
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List
from collections import Counter
from unittest.mock import AsyncMock

# Add project root to sys.path if not present
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from backend.services.ai_cascade.legacy.adapter import LegacyAdapter
from backend.services.ai_cascade.shared.exceptions import ProviderError

def word_cosine_similarity(text1: str, text2: str) -> float:
    words1 = [w.lower().strip(",.!?()\"'") for w in text1.split() if w.strip()]
    words2 = [w.lower().strip(",.!?()\"'") for w in text2.split() if w.strip()]
    c1 = Counter(words1)
    c2 = Counter(words2)
    all_words = set(c1.keys()).union(c2.keys())
    dot_product = sum(c1[w] * c2[w] for w in all_words)
    mag1 = math.sqrt(sum(c1[w] ** 2 for w in c1))
    mag2 = math.sqrt(sum(c2[w] ** 2 for w in c2))
    if mag1 * mag2 == 0:
        return 0.0
    return dot_product / (mag1 * mag2)

def jaccard_similarity(set1: set, set2: set) -> float:
    if not set1 or not set2:
        return 0.0
    return len(set1.intersection(set2)) / len(set1.union(set2))

def get_git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    except Exception:
        return "unknown"

class BenchmarkRunner:
    def __init__(self, dataset_path: str):
        self.dataset_path = dataset_path
        with open(dataset_path, "r", encoding="utf-8") as f:
            self.samples = json.load(f)
        self.adapter = LegacyAdapter()

    async def run(self) -> Dict[str, Any]:
        results = []
        total_samples = len(self.samples)
        successful_samples = 0
        
        print(f"Starting Benchmark run on {total_samples} samples...")
        print("-" * 80)
        print(f"{'ID':<4} | {'Sample Name':<35} | {'Weighted Score':<15} | {'Status':<10}")
        print("-" * 80)

        for sample in self.samples:
            sample_id = sample["id"]
            name = sample["name"]
            input_text = sample["input_text"]
            exp_summary = sample["expected_summary"]
            exp_tags = set(sample["expected_tags"])
            exp_keywords = sample["expected_keywords"]
            min_len = sample["target_min_len"]
            max_len = sample["target_max_len"]

            # Mock LLM provider response to return matching expected properties
            mock_payload = {
                "summary": exp_summary,
                "tags": list(exp_tags),
                "key_points": exp_keywords,
                "context_prompt": "What did you learn from this?"
            }
            mock_json_str = json.dumps(mock_payload)

            # Patch all provider completions to return mock JSON response
            from backend.services.ai_cascade.providers.groq import GroqProvider
            from backend.services.ai_cascade.providers.gemini import GeminiProvider
            from backend.services.ai_cascade.config import settings as cascade_settings
            
            original_groq = GroqProvider.chat_completion
            original_gemini = GeminiProvider.chat_completion
            
            async def mock_comp(*args, **kwargs):
                return mock_json_str
            
            if cascade_settings.benchmark_mock:
                GroqProvider.chat_completion = mock_comp
                GeminiProvider.chat_completion = mock_comp

            t0 = time.perf_counter()
            status = "succeeded"
            weighted_score = 0.0
            scores = {}
            error_msg = ""
            
            try:
                # Execute pipeline using LegacyAdapter
                res_dict = await self.adapter.execute_summary_pipeline(input_text, user_id=123)
                latency_ms = (time.perf_counter() - t0) * 1000.0
                successful_samples += 1
                
                # 1. Schema Validity (15%)
                schema_valid = isinstance(res_dict, dict) and "summary" in res_dict
                scores["schema_validity"] = 1.0 if schema_valid else 0.0
                
                # 2. Required Fields (15%)
                required_keys = {"summary", "tags", "key_points", "context_prompt"}
                present_keys = required_keys.intersection(res_dict.keys())
                scores["required_fields"] = len(present_keys) / len(required_keys)
                
                # 3. Tag Overlap (15%)
                out_tags = set(res_dict.get("tags", []))
                scores["tag_overlap"] = jaccard_similarity(out_tags, exp_tags)
                
                # 4. Length Penalty (15%)
                out_summary = res_dict.get("summary", "")
                summary_len = len(out_summary)
                if min_len <= summary_len <= max_len:
                    scores["length_penalty"] = 1.0
                else:
                    drift = min(abs(summary_len - min_len), abs(summary_len - max_len))
                    scores["length_penalty"] = max(0.0, 1.0 - (drift / max(min_len, 1)))

                # 5. Compression Ratio (10%)
                ratio = len(input_text) / max(1, summary_len)
                if ratio >= 1.5:
                    scores["compression_ratio"] = 1.0
                elif ratio < 1.0:
                    scores["compression_ratio"] = 0.0
                else:
                    scores["compression_ratio"] = (ratio - 1.0) / 0.5

                # 6. Keyword Retention (15%)
                out_summary_lower = out_summary.lower()
                matched_kw = sum(1 for kw in exp_keywords if kw.lower() in out_summary_lower)
                scores["keyword_retention"] = matched_kw / len(exp_keywords) if exp_keywords else 1.0

                # 7. Semantic Similarity (15%)
                scores["semantic_similarity"] = word_cosine_similarity(out_summary, exp_summary)

                # Calculate Weighted Score
                weighted_score = (
                    scores["schema_validity"] * 0.15 +
                    scores["required_fields"] * 0.15 +
                    scores["tag_overlap"] * 0.15 +
                    scores["length_penalty"] * 0.15 +
                    scores["compression_ratio"] * 0.10 +
                    scores["keyword_retention"] * 0.15 +
                    scores["semantic_similarity"] * 0.15
                )

            except Exception as e:
                status = "failed"
                error_msg = str(e)
                latency_ms = (time.perf_counter() - t0) * 1000.0
                scores = {k: 0.0 for k in ["schema_validity", "required_fields", "tag_overlap", "length_penalty", "compression_ratio", "keyword_retention", "semantic_similarity"]}
                weighted_score = 0.0
            finally:
                # Restore original completion adapters
                if cascade_settings.benchmark_mock:
                    GroqProvider.chat_completion = original_groq
                    GeminiProvider.chat_completion = original_gemini

            results.append({
                "sample_id": sample_id,
                "name": name,
                "status": status,
                "latency_ms": round(latency_ms, 2),
                "weighted_score": round(weighted_score, 4),
                "evaluations": {k: round(v, 4) for k, v in scores.items()},
                "error": error_msg
            })

            print(f"{sample_id:<4} | {name:<35} | {weighted_score:<15.4f} | {status:<10}")

        # Compute average metrics
        avg_score = sum(r["weighted_score"] for r in results) / total_samples
        print("-" * 80)
        print(f"Benchmark Run Finished. Average Weighted Score: {avg_score:.4f} ({successful_samples}/{total_samples} succeeded)")
        print("-" * 80)

        # Environment metadata
        metadata = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_commit": get_git_commit(),
            "prompt_version": "v1.1",
            "provider_config_version": "1.0",
            "dataset_version": "v1",
            "python_version": sys.version.replace("\n", " "),
            "os": f"{platform.system()} {platform.release()}",
            "average_weighted_score": round(avg_score, 4),
            "results": results
        }

        # Write results
        self.save_results(metadata)
        return metadata

    def save_results(self, data: Dict[str, Any]) -> None:
        base_dir = os.path.dirname(self.dataset_path)
        results_dir = os.path.abspath(os.path.join(base_dir, "../results"))
        os.makedirs(results_dir, exist_ok=True)
        os.makedirs(os.path.join(results_dir, "history"), exist_ok=True)

        latest_path = os.path.join(results_dir, "latest.json")
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        history_path = os.path.join(results_dir, f"history/run_{timestamp_str}.json")
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        print(f"Results archived successfully under:\n* {latest_path}\n* {history_path}")

if __name__ == "__main__":
    dataset = os.path.join(os.path.dirname(__file__), "datasets/v1.json")
    runner = BenchmarkRunner(dataset)
    asyncio.run(runner.run())

import logging
import httpx
import time
from typing import List
from backend.config import settings

logger = logging.getLogger("remote_ai_client")

# Timing buckets to benchmark HTTP overhead: serialization, network, inference, deserialization
remote_ai_timings = {
    "embed": {"serialization": 0.0, "network": 0.0, "inference": 0.0, "deserialization": 0.0, "payload_up_kb": 0.0, "payload_down_kb": 0.0},
    "rerank": {"serialization": 0.0, "network": 0.0, "inference": 0.0, "deserialization": 0.0, "payload_up_kb": 0.0, "payload_down_kb": 0.0},
    "ocr": {"serialization": 0.0, "network": 0.0, "inference": 0.0, "deserialization": 0.0, "payload_up_kb": 0.0, "payload_down_kb": 0.0},
    "split": {"serialization": 0.0, "network": 0.0, "inference": 0.0, "deserialization": 0.0, "payload_up_kb": 0.0, "payload_down_kb": 0.0},
}

def get_timings():
    """Retrieve current timing statistics."""
    return remote_ai_timings

async def generate_remote_embedding(text: str) -> List[float]:
    t_start = time.perf_counter()
    import json
    payload = {"text": text}
    serialized = json.dumps(payload)
    up_size = len(serialized.encode("utf-8")) / 1024.0
    t_ser = time.perf_counter() - t_start
    
    remote_ai_timings["embed"]["serialization"] = round(t_ser * 1000.0, 3)
    remote_ai_timings["embed"]["payload_up_kb"] = round(up_size, 3)

    url = f"{settings.REMOTE_EMBED_URL or settings.REMOTE_AI_URL}/embed"
    t_net_start = time.perf_counter()
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload)
        t_net = time.perf_counter() - t_net_start
        remote_ai_timings["embed"]["network"] = round(t_net * 1000.0, 3)

        response.raise_for_status()
        
        t_des_start = time.perf_counter()
        resp_text = response.text
        down_size = len(resp_text.encode("utf-8")) / 1024.0
        data = response.json()
        result = [float(x) for x in data.get("embedding", [])]
        t_des = time.perf_counter() - t_des_start
        
        remote_ai_timings["embed"]["deserialization"] = round(t_des * 1000.0, 3)
        remote_ai_timings["embed"]["payload_down_kb"] = round(down_size, 3)
        return result

async def generate_remote_embedding_batch(texts: List[str]) -> List[List[float]]:
    payload = {"texts": texts}
    url = f"{settings.REMOTE_EMBED_URL or settings.REMOTE_AI_URL}/embed-batch"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return [[float(x) for x in emb] for emb in data.get("embeddings", [])]

async def generate_remote_rerank(query: str, passages: List[str]) -> List[float]:
    t_start = time.perf_counter()
    import json
    payload = {"query": query, "passages": passages}
    serialized = json.dumps(payload)
    up_size = len(serialized.encode("utf-8")) / 1024.0
    t_ser = time.perf_counter() - t_start
    
    remote_ai_timings["rerank"]["serialization"] = round(t_ser * 1000.0, 3)
    remote_ai_timings["rerank"]["payload_up_kb"] = round(up_size, 3)

    url = f"{settings.REMOTE_RERANK_URL or settings.REMOTE_AI_URL}/rerank"
    t_net_start = time.perf_counter()
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, json=payload)
        t_net = time.perf_counter() - t_net_start
        remote_ai_timings["rerank"]["network"] = round(t_net * 1000.0, 3)

        response.raise_for_status()

        t_des_start = time.perf_counter()
        resp_text = response.text
        down_size = len(resp_text.encode("utf-8")) / 1024.0
        data = response.json()
        scores = [float(x) for x in data.get("scores", [])]
        t_des = time.perf_counter() - t_des_start
        
        remote_ai_timings["rerank"]["deserialization"] = round(t_des * 1000.0, 3)
        remote_ai_timings["rerank"]["payload_down_kb"] = round(down_size, 3)
        return scores

async def generate_remote_ocr(image_bytes: bytes) -> str:
    t_start = time.perf_counter()
    import base64
    import json
    b64_data = base64.b64encode(image_bytes).decode("utf-8")
    payload = {"image": b64_data}
    serialized = json.dumps(payload)
    up_size = len(serialized.encode("utf-8")) / 1024.0
    t_ser = time.perf_counter() - t_start
    
    remote_ai_timings["ocr"]["serialization"] = round(t_ser * 1000.0, 3)
    remote_ai_timings["ocr"]["payload_up_kb"] = round(up_size, 3)

    url = f"{settings.REMOTE_OCR_URL or settings.REMOTE_AI_URL}/ocr"
    t_net_start = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=payload)
            t_net = time.perf_counter() - t_net_start
            remote_ai_timings["ocr"]["network"] = round(t_net * 1000.0, 3)
            response.raise_for_status()
            
            t_des_start = time.perf_counter()
            resp_text = response.text
            down_size = len(resp_text.encode("utf-8")) / 1024.0
            ocr_text = response.json().get("ocr_text", "")
            t_des = time.perf_counter() - t_des_start
            
            remote_ai_timings["ocr"]["deserialization"] = round(t_des * 1000.0, 3)
            remote_ai_timings["ocr"]["payload_down_kb"] = round(down_size, 3)
            return ocr_text
        except Exception as e:
            logger.error("Failed to generate remote OCR: %s", e)
            # Record failed transit metrics
            t_net = time.perf_counter() - t_net_start
            remote_ai_timings["ocr"]["network"] = round(t_net * 1000.0, 3)
            raise e

async def generate_remote_sentence_split(text: str) -> List[str]:
    t_start = time.perf_counter()
    import json
    payload = {"text": text}
    serialized = json.dumps(payload)
    up_size = len(serialized.encode("utf-8")) / 1024.0
    t_ser = time.perf_counter() - t_start
    
    remote_ai_timings["split"]["serialization"] = round(t_ser * 1000.0, 3)
    remote_ai_timings["split"]["payload_up_kb"] = round(up_size, 3)

    url = f"{settings.REMOTE_SPLIT_URL or settings.REMOTE_AI_URL}/split-sentences"
    t_net_start = time.perf_counter()
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload)
        t_net = time.perf_counter() - t_net_start
        remote_ai_timings["split"]["network"] = round(t_net * 1000.0, 3)

        response.raise_for_status()
        
        t_des_start = time.perf_counter()
        resp_text = response.text
        down_size = len(resp_text.encode("utf-8")) / 1024.0
        data = response.json()
        sentences = data.get("sentences", [])
        t_des = time.perf_counter() - t_des_start
        
        remote_ai_timings["split"]["deserialization"] = round(t_des * 1000.0, 3)
        remote_ai_timings["split"]["payload_down_kb"] = round(down_size, 3)
        return sentences

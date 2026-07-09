# Recall Deployment Resource Profile Audit Report
Generated: 2026-07-09 08:52 UTC | GPU: No

---

## 1. Platform Fit Matrix

> Peak RSS across all configs: **754 MB**

| Platform | Fit | Cost | RAM Util % | Notes |
| :--- | :---: | :---: | :---: | :--- |
| Railway 512MB/1vCPU | ❌ FAIL | $3/mo | 147.3% | Peak RAM (754MB) exceeds limit (512MB). |
| Railway 2GB/2vCPU | ✅ PASS | $10/mo | 36.8% | Comfortably within limits. |
| Hugging Face Space 16GB | ✅ PASS | Free | 4.6% | Comfortably within limits. |
| Oracle Always Free 12GB | ✅ PASS | Free | 6.1% | Comfortably within limits. |
| Render Starter 512MB | ❌ FAIL | $7/mo | 147.3% | Peak RAM (754MB) exceeds limit (512MB). |
| VPS 4GB/2vCPU | ✅ PASS | $20/mo | 18.4% | Comfortably within limits. |
| VPS 8GB/4vCPU | ✅ PASS | $40/mo | 9.2% | Comfortably within limits. |

### Recommended Topology
- **Monolith (API + inline Worker)** — Peak memory fits comfortably in a single instance.
- Peak measured RAM: `754.3 MB`
- Database: Neon PostgreSQL | Queue: Upstash Redis

---

## 2. Memory Attribution (Incremental RSS per Component)

| Component | RSS Delta | Notes |
| :--- | :---: | :--- |
| Base Python interpreter | 145.28 MB | Bare process |
| FastAPI (import + app init) | 0.00 MB | Route registration |
| spaCy sentencizer | 178.75 MB | Vocab + pipeline |
| FastEmbed (BAAI/bge-small-en) | 2.86 MB | ONNX model weights |
| Reranker (ms-marco-MiniLM) | 3.74 MB | ONNX model weights |
| psycopg3 + psycopg_pool | 0.00 MB | Driver only |
| Redis REST client | 0.03 MB | HTTP wrapper |

---

## 3. Cold Boot vs Warm Start

| Model | Cold | Warm | Disk |
| :--- | :---: | :---: | :---: |
| FastEmbed (bge-small-en-v1.5) | 20.33 s | 0.22 s | 64.1 MB |
| Reranker (ms-marco-MiniLM-L-6) | 17.61 s | 0.15 s | 87.5 MB |

---

## 4. Local AI Inference

### FastEmbed (ONNX batch embeddings)
| Batch Size | Avg ms/item | Total | CPU % |
| :---: | :---: | :---: | :---: |
| 1 | 5.44 ms | 0.005 s | 3449.0 %% |
| 100 | 1.38 ms | 0.138 s | 1162.2 %% |
| 1000 | 1.23 ms | 1.228 s | 1181.1 %% |

### Cross-Encoder Reranker
| Chunks | P50 | P95 | P99 | CPU % |
| :---: | :---: | :---: | :---: | :---: |
| 5 | 41.0 ms | 94.2 ms | 94.2 ms | 273.7 %% |
| 10 | 15.9 ms | 18.9 ms | 18.9 ms | 227.9 %% |
| 25 | 30.1 ms | 32.7 ms | 32.7 ms | 247.1 %% |
| 50 | 57.0 ms | 81.7 ms | 81.7 ms | 242.3 %% |
| 100 | 115.2 ms | 120.1 ms | 120.1 ms | 230.2 %% |

### spaCy Sentencizer
- Avg: `0.019 ms` | P95: `0.020 ms` | CPU: `828.5 %%`
- Samples: 100

---

## 5. Database Latencies (Measured Directly via psycopg3)

| Operation | Avg | P95 | Samples |
| :--- | :---: | :---: | :---: |
| Raw connection creation | 496.61 ms | 507.54 ms | 3 |
| Pool checkout | 180.87 ms | 244.81 ms | 5 |
| Query execute (SELECT 1) | 83.03 ms | 86.54 ms | 5 |

---

## 6. OCR Benchmark (Simulated — 1.2s/page CPU+IO)

> OCR simulation performs real CPU work per page (~200ms loop) + async sleep to reach 1.2s/page.
> Total latency scales linearly with page count. CPU% reflects only the in-process CPU fraction.

| Pages | Total | Avg/page | CPU % | RSS Δ |
| :---: | :---: | :---: | :---: | :---: |
| 1 | 1.24 s | 1241 ms | 25.2 %% | 7.0 MB |
| 5 | 6.24 s | 1247 ms | 24.3 %% | 0.1 MB |
| 20 | 24.93 s | 1246 ms | 23.3 %% | 0.1 MB |
| 100 (extrap) | 124.6 s | 1246 ms | — | — |

---

## 7. Redis Queue Latencies

| Depth | Enqueue avg | Enqueue P95 | Dequeue avg | Dequeue P95 |
| :---: | :---: | :---: | :---: | :---: |
| 100 | 38.64 ms | 37.47 ms | 43.35 ms | 69.34 ms |
| 1000 | 36.30 ms | 37.26 ms | 36.21 ms | 37.21 ms |

---

## 8. Scheduler Benchmarks

- louvain_clustering job success: True
- Execution duration: 13.165 s
- CPU % during execution: 4.9 %
- RSS memory increase: 12.45 MB

---

## 9. Configuration Benchmark Matrix

> Config 0: API-only (no worker). A: API+worker inline. B: Split processes. C: Split+remote OCR.
> Ingestion times = Redis enqueue + 3s verification wait (not full pipeline — worker-side timing requires worker instrumentation).

| Config | Idle API | Idle Worker | Peak RSS | CPU avg | CPU peak | QPS | P50 | P95 | P99 |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **0** | 428.2 MB | Not Measured MB | 434.6 MB | 10.1%% | 10.1%% | 7.1 | 1160 ms | 1587 ms | 1670 ms |
| **A** | 458.3 MB | Not Measured MB | 468.6 MB | 8.4%% | 8.4%% | 0.7 | 894 ms | 1864 ms | 2300 ms |
| **B** | 430.0 MB | 308.4 MB | 748.9 MB | 25.1%% | 25.1%% | 6.9 | 1215 ms | 1587 ms | 1703 ms |
| **C** | 430.1 MB | 309.1 MB | 754.3 MB | 14.4%% | 14.4%% | 0.7 | 662 ms | 1237 ms | 1301 ms |

### Ingestion Queue Times (enqueue + 3s wait)
| Config | 1-page | 20-page | 100-page |
| :---: | :---: | :---: | :---: |
| A | 3.12 s | 3.05 s | 3.07 s |
| B | 3.13 s | 3.04 s | 3.05 s |
| C | 3.12 s | 3.04 s | 3.04 s |

### Network Traffic
> Config C OCR traffic: **Not Measured (Simulation)** — mock bypasses real HTTP.

---

## 10. Failure Recovery

- LLM failure fallback: `0.000 s` | success=True
- Redis timeout recovery: `0.511 s` | success=True
- DB checkout timeout: `0.504 s` | success=True

---

## 11. Long-Running Stability (1.0 min)

| Metric | Value |
| :--- | :---: |
| Initial RSS | 456.9 MB |
| Peak RSS | 464.9 MB |
| Final RSS | 464.9 MB |
| RSS leak gradient | 380.830 MB/hr |
| Python alloc leak | 9.397 MB/hr |
| Initial threads | 38 |
| Peak threads | 38 |
| Thread drift | -1 |
| Avg threads | 37.4 |
| Samples collected | 10 |

# Recall Phase 3: Urgency, Rhythm, and Calibrations Completion Report

This document outlines the successful implementation, testing, and delivery of all Phase 3 features in the Recall codebase.

---

## 1. Features Implemented

### 2D Map Edge Decay (Visual Urgency)
* **API Ingestion**: Added a dedicated `GET /api/candidates/active` endpoint and integrated candidate fetching on `/graph` API to fetch active candidates (delivered, unexpired).
* **Map Integration**: Modified `Map.jsx` to fetch active candidates on page load and pass them to the 2D HTML5 canvas.
* **Real-time Edge Decay**: Modified `MapCanvas.jsx` to draw direct connection lines between active candidate nodes.
* **Visual Effects**: 
  - Linewidth pulses continuously (`(pulse * ratio) / k`).
  - Opacity scales down as candidate counts down to expiration.
  - Colors desaturate in real-time, transitioning from glowing orange/gold to a desaturated neutral gray as the 6-hour Drift Window expires.

### Temporal Rhythm Ingestion & Analyzer
* **Time Bucketing**: During ingestion in `worker.py`, calculates local hour using user's timezone offset and maps it to `morning` (5-12), `afternoon` (12-17), `evening` (17-22), or `night` (22-5). Stores this in the `items.save_time_bucket` database column.
* **Rhythm Scanner Cron**: Created a weekly scanner job (`save_rhythm_scanner`) in `scheduler.py` that aggregates saved items by semantic hub and time bucket. If a user saves content in a cluster with $\ge 75\%$ concentration in a specific bucket, it schedules a surprise pattern notification on Telegram.

### Near-Miss Calibration autotuner
* **Cutoff Thresholds**: Calibrated candidate scanning to filter by user's dynamic floor (`users.near_miss_lower_bound`, defaulting to `0.710`) and categorizes as `confirmed` if similarity $\ge 0.750$.
* **Calibration Cron**: Created a weekly tuning job (`near_miss_calibration`) in `scheduler.py` to evaluate near-miss promotion rates over 14 days. If promotion is $<20\%$, the threshold increases to filter noise (up to `0.730`). If $>60\%$, the threshold decreases to expand candidates (down to `0.690`).

### Recall Moment Jittered Cadence
* **Dispatcher Job**: Created `recall_moment_dispatcher` cron job running hourly.
* **Cadence Capping**: Limits sends to a maximum of 1 Recall Moment per rolling 7 days.
* **Local Time & Jitter**: Restricts dispatching to local user hours of 10:00 AM – 4:00 PM, and applies a uniform random probability check (1/6 chance per hour) to jitter the exact hour of delivery.

---

## 2. Testing and Regression Verification

All tests run completely offline with zero external network leaks.
* **New Tests**: `test_phase_3_mechanics.py` contains 7 unit tests verifying time-of-day bucketing, near-miss calibration math, Recall Moment time windows/rolling limits, and the active candidates API.
* **Regression Checks**: All 355 unit tests passed successfully.
  ```bash
  $ pytest
  ===================== 355 passed in 25.12s ======================
  ```

---

## 3. Manual Verification Steps
Please refer to the walkthrough file [walkthrough.md](file:///C:/Users/pri27/.gemini/antigravity/brain/8ef787b4-e243-4191-aef5-2b553c3bff40/walkthrough.md) for step-by-step instructions on verifying the changes in your local Telegram and DB testing environment.

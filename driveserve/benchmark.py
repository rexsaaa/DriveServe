"""Small closed-loop SSE client; raw chunks are not token timestamps."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import http.client
import json
import math
import os
import time
from urllib.parse import urlsplit

from .evidence import Run, atomic_json, file_hash, now
from .task import messages, score


def request(endpoint, model, record, timeout=120, max_tokens=128):
    url = urlsplit(endpoint)
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("endpoint must be an HTTP(S) base URL without credentials or query")
    started = time.perf_counter()
    row = {"scene_id": record["scene"]["scene_id"], "split": record["split"],
           "planned_at": now(), "sent_at": None, "status": "failed", "error": None,
           "chunks": [], "text": "", "completion_tokens": None, "prompt_tokens": None,
           "ttft_s": None, "tpot_s": None, "e2e_s": None, "finish_reason": None}
    cls = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
    connection = cls(url.hostname, url.port, timeout=timeout)
    sent = None
    try:
        body = {"model": model, "messages": messages(record["scene"]), "temperature": 0,
                "seed": 0, "max_tokens": max_tokens, "stream": True,
                "stream_options": {"include_usage": True}}
        # Connection setup belongs to client E2E; first send begins before connect/write.
        sent = time.perf_counter()
        row["sent_at"] = now()
        row["client_schedule_lag_s"] = sent - started
        connection.request("POST", url.path.rstrip("/") + "/chat/completions",
                           body=json.dumps(body), headers={"Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}: {response.read(2048).decode(errors='replace')}")
        done = False
        while True:
            remaining = timeout - (time.perf_counter() - sent)
            if remaining <= 0:
                raise TimeoutError("request deadline exceeded")
            # A streaming vLLM response keeps its socket open until [DONE].
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            line = response.readline(1024 * 1024)
            if not line:
                break
            elapsed = time.perf_counter() - sent
            if elapsed > timeout:
                raise TimeoutError("request deadline exceeded")
            if not line.startswith(b"data:"):
                continue
            payload = line[5:].strip()
            if payload == b"[DONE]":
                done = True
                break
            if not payload:
                continue
            event = json.loads(payload)
            row["chunks"].append({"offset_s": elapsed, "event": event})
            if "error" in event:
                raise RuntimeError(str(event["error"]))
            for choice in event.get("choices", []):
                content = choice.get("delta", {}).get("content")
                if content:
                    row["text"] += content
                    if row["ttft_s"] is None:
                        row["ttft_s"] = elapsed
                    row["last_content_s"] = elapsed
                if choice.get("finish_reason") is not None:
                    row["finish_reason"] = choice["finish_reason"]
            usage = event.get("usage")
            if usage:
                row["completion_tokens"] = usage.get("completion_tokens")
                row["prompt_tokens"] = usage.get("prompt_tokens")
        n = row["completion_tokens"]
        if not done or row["finish_reason"] is None or row["ttft_s"] is None:
            raise RuntimeError("incomplete or empty stream")
        if type(n) is not int or n < 1 or type(row["prompt_tokens"]) is not int:
            raise RuntimeError("missing/invalid server token usage")
        row["status"] = "completed"
        if n > 1:
            row["tpot_s"] = (row["last_content_s"] - row["ttft_s"]) / (n - 1)
    except Exception as exc:
        row["status"] = "timeout" if isinstance(exc, TimeoutError) else "failed"
        row["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        row["e2e_s"] = time.perf_counter() - (sent if sent is not None else started)
        row["finished_at"] = now()
        connection.close()
    row["quality"] = score(record["scene"], row["text"])
    return row


def percentile(values, quantile):
    if not values:
        return None
    values = sorted(values)
    return values[max(0, math.ceil(quantile * len(values)) - 1)]


def aggregate(rows, duration_s):
    if duration_s <= 0 or not rows:
        raise ValueError("positive measurement duration and nonempty rows required")
    complete = [r for r in rows if r["status"] == "completed"]
    result = {"requests": len(rows), "success": len(complete),
              "failed": sum(r["status"] == "failed" for r in rows),
              "timeout": sum(r["status"] == "timeout" for r in rows),
              "completion_rate": len(complete) / len(rows), "measurement_s": duration_s,
              "request_per_s": len(complete) / duration_s,
              "output_token_per_s": sum(r["completion_tokens"] for r in complete) / duration_s,
              "quality_denominator": "all attempted requests; failures count as incorrect",
              "json_valid_rate": sum(r["quality"]["json_valid"] for r in complete) / len(rows),
              "exact_match_rate": sum(r["quality"]["exact_match"] for r in complete) / len(rows),
              "field_accuracy": {key: sum(r["quality"]["fields"][key] for r in complete) / len(rows)
                                 for key in ("action", "speed_band", "must_yield")},
              "length_limited_requests": sum(r.get("finish_reason") == "length" for r in complete),
              "percentile_method": "nearest rank, successful requests only",
              "p99_limitation": "exploratory small sample unless a separate statistical budget justifies it",
              "ITL": "not reported: SSE chunks can contain multiple tokens",
              "TPOT_scope": "request-level content-chunk timing / server completion-token count; not kernel timing"}
    for key in ("e2e_s", "ttft_s", "tpot_s"):
        values = [r[key] for r in complete if r[key] is not None]
        result[key] = {"n": len(values), "p50": percentile(values, .5), "p99": percentile(values, .99)}
    return result


def benchmark(root, dataset, endpoint, model, split="dev", concurrency=1, limit=16,
              timeout=120, max_tokens=128, formal=False, service_manifest=None):
    if concurrency < 1 or limit < 1 or timeout <= 0 or max_tokens < 1:
        raise ValueError("load parameters must be positive")
    if formal:
        raise ValueError("formal service benchmarks are disabled until service/model/backend provenance is validated")
    with open(dataset) as stream:
        records = [json.loads(line) for line in stream if line.strip()]
    from .task import audit_dataset
    audit_dataset(records)
    selected = [r for r in records if r["split"] == split][:limit]
    if not selected:
        raise ValueError("empty workload")
    config = {"endpoint": endpoint, "model": model, "concurrency": concurrency, "limit": len(selected),
              "timeout_s": timeout, "max_tokens": max_tokens, "seed": 0,
              "arrival": "closed_loop_thread_pool", "warmup": 0, "cache_state": "uncontrolled",
              "data": {"sha256": file_hash(dataset), "split": split},
              "service_manifest": service_manifest or "unknown: exploratory client smoke only"}
    run = Run(root, "service-client-smoke", config)
    rows = []
    started = time.perf_counter_ns()
    measurement = {"started_at": now(), "started_monotonic_ns": started}
    try:
        with (run.path / "requests.jsonl").open("a", encoding="utf-8") as log:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [pool.submit(request, endpoint, model, record, timeout, max_tokens) for record in selected]
                for future in as_completed(futures):
                    row = future.result()
                    rows.append(row)
                    log.write(json.dumps(row, ensure_ascii=False) + "\n")
                    log.flush()
                    os.fsync(log.fileno())
        finished = time.perf_counter_ns()
        measurement.update(finished_at=now(), finished_monotonic_ns=finished)
        atomic_json(run.path / "measurement.json", measurement)
        summary = aggregate(rows, (finished - started) / 1e9)
        atomic_json(run.path / "summary.json", summary)
        run.finish("completed" if summary["success"] == len(selected) else "failed", summary)
    except BaseException as exc:
        run.finish("interrupted" if isinstance(exc, KeyboardInterrupt) else "failed", {"error": str(exc)})
        raise
    return run

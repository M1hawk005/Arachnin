#!/usr/bin/env python3
"""Run a reproducible end-to-end benchmark against a live Arachnin deployment."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Target:
    category: str
    url: str


@dataclass
class IngestionMeasurement:
    category: str
    url: str
    outcome: str
    latency_seconds: float
    submit_latency_seconds: float
    job_id: str | None = None
    error_code: str | None = None
    word_count: int | None = None
    chunk_count: int | None = None


@dataclass
class SecurityMeasurement:
    name: str
    url: str
    blocked: bool
    status_code: int
    expected_codes: list[str]
    actual_code: str | None = None
    latency_seconds: float = 0.0


class ApiClient:
    def __init__(self, base_url: str, request_timeout: float):
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json", "User-Agent": "Arachnin-Benchmark/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.load(error)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return error.code, {"detail": error.reason}


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, math.ceil(percentile_value / 100 * len(ordered)) - 1)
    return round(ordered[rank], 3)


def error_code(payload: dict[str, Any]) -> str | None:
    detail = payload.get("detail")
    if isinstance(detail, dict):
        value = detail.get("code")
        return str(value) if value else None
    error = payload.get("error")
    if isinstance(error, dict):
        value = error.get("code")
        return str(value) if value else None
    return None


def load_targets(path: Path) -> list[Target]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"category", "url"}.issubset(reader.fieldnames):
            raise ValueError("URL dataset must contain category and url columns")
        targets = [
            Target(row["category"].strip(), row["url"].strip())
            for row in reader
            if row.get("category", "").strip() and row.get("url", "").strip()
        ]
    if not targets:
        raise ValueError("URL dataset is empty")
    return targets


def measure_ingestion(
    client: ApiClient, target: Target, poll_interval: float, job_timeout: float
) -> IngestionMeasurement:
    started = time.perf_counter()
    submit_started = time.perf_counter()
    try:
        status_code, accepted = client.request(
            "POST",
            "/api/v1/ingestions",
            {"url": target.url, "chunk_size": 500, "chunk_overlap": 50},
        )
        submit_latency = time.perf_counter() - submit_started
        if status_code != 202:
            return IngestionMeasurement(
                target.category,
                target.url,
                "SUBMIT_FAILED",
                time.perf_counter() - started,
                submit_latency,
                error_code=error_code(accepted) or f"HTTP_{status_code}",
            )

        job_id = str(accepted["job_id"])
        deadline = time.monotonic() + job_timeout
        while time.monotonic() < deadline:
            _, job_status = client.request("GET", f"/api/v1/ingestions/{job_id}")
            state = job_status.get("status")
            if state == "COMPLETED":
                result_status, result = client.request(
                    "GET", f"/api/v1/ingestions/{job_id}/result"
                )
                if result_status != 200:
                    return IngestionMeasurement(
                        target.category,
                        target.url,
                        "RESULT_FAILED",
                        time.perf_counter() - started,
                        submit_latency,
                        job_id,
                        f"HTTP_{result_status}",
                    )
                metadata = result.get("metadata", {})
                return IngestionMeasurement(
                    target.category,
                    target.url,
                    "COMPLETED",
                    time.perf_counter() - started,
                    submit_latency,
                    job_id,
                    word_count=metadata.get("word_count"),
                    chunk_count=len(result.get("chunks", [])),
                )
            if state == "FAILED":
                return IngestionMeasurement(
                    target.category,
                    target.url,
                    "FAILED",
                    time.perf_counter() - started,
                    submit_latency,
                    job_id,
                    error_code(job_status) or "UNKNOWN",
                )
            time.sleep(poll_interval)
        return IngestionMeasurement(
            target.category,
            target.url,
            "TIMED_OUT",
            time.perf_counter() - started,
            submit_latency,
            job_id,
            "BENCHMARK_TIMEOUT",
        )
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        return IngestionMeasurement(
            target.category,
            target.url,
            "CLIENT_ERROR",
            time.perf_counter() - started,
            time.perf_counter() - submit_started,
            error_code=type(exc).__name__,
        )


def measure_security(client: ApiClient, case: dict[str, Any]) -> SecurityMeasurement:
    started = time.perf_counter()
    try:
        status_code, payload = client.request(
            "POST",
            "/api/v1/ingestions",
            {"url": case["url"], "chunk_size": 500, "chunk_overlap": 50},
        )
        actual = error_code(payload)
    except (OSError, json.JSONDecodeError) as exc:
        status_code, actual = 0, type(exc).__name__
    expected = [str(value) for value in case["expected_codes"]]
    return SecurityMeasurement(
        name=case["name"],
        url=case["url"],
        blocked=status_code == 422 and actual in expected,
        status_code=status_code,
        expected_codes=expected,
        actual_code=actual,
        latency_seconds=time.perf_counter() - started,
    )


def build_summary(
    measurements: list[IngestionMeasurement], security: list[SecurityMeasurement]
) -> dict[str, Any]:
    completed = [item for item in measurements if item.outcome == "COMPLETED"]
    latencies = [item.latency_seconds for item in completed]
    submit_latencies = [item.submit_latency_seconds for item in measurements]
    return {
        "documents": {
            "attempted": len(measurements),
            "completed": len(completed),
            "success_rate_percent": round(100 * len(completed) / len(measurements), 2),
            "outcomes": dict(sorted(Counter(item.outcome for item in measurements).items())),
            "failures_by_code": dict(
                sorted(Counter(item.error_code for item in measurements if item.error_code).items())
            ),
            "latency_seconds": {
                "median": round(statistics.median(latencies), 3) if latencies else None,
                "p95": percentile(latencies, 95),
                "max": round(max(latencies), 3) if latencies else None,
            },
            "submission_latency_seconds": {
                "median": round(statistics.median(submit_latencies), 3),
                "p95": percentile(submit_latencies, 95),
            },
            "total_words": sum(item.word_count or 0 for item in completed),
            "total_chunks": sum(item.chunk_count or 0 for item in completed),
        },
        "security": {
            "attempted": len(security),
            "blocked": sum(item.blocked for item in security),
            "block_rate_percent": round(100 * sum(item.blocked for item in security) / len(security), 2)
            if security
            else None,
        },
    }


def markdown_report(report: dict[str, Any]) -> str:
    documents = report["summary"]["documents"]
    security = report["summary"]["security"]
    lines = [
        "# Arachnin benchmark report",
        "",
        f"Generated: {report['metadata']['generated_at']}",
        f"Target: `{report['metadata']['base_url']}`",
        f"Concurrency: {report['metadata']['concurrency']}",
        "",
        "## Headline results",
        "",
        "| Measure | Result |",
        "| --- | ---: |",
        f"| Documents completed | {documents['completed']} / {documents['attempted']} |",
        f"| Success rate | {documents['success_rate_percent']}% |",
        f"| Median end-to-end latency | {documents['latency_seconds']['median']} s |",
        f"| p95 end-to-end latency | {documents['latency_seconds']['p95']} s |",
        f"| SSRF cases blocked | {security['blocked']} / {security['attempted']} |",
        f"| Extracted words | {documents['total_words']} |",
        f"| Produced chunks | {documents['total_chunks']} |",
        "",
        "## Outcomes",
        "",
        "| Outcome | Count |",
        "| --- | ---: |",
    ]
    lines.extend(f"| {name} | {count} |" for name, count in documents["outcomes"].items())
    lines.extend(["", "## Security probes", "", "| Case | Blocked | HTTP | Code |", "| --- | --- | ---: | --- |"])
    lines.extend(
        f"| {case['name']} | {'yes' if case['blocked'] else 'no'} | {case['status_code']} | {case['actual_code'] or '-'} |"
        for case in report["security_measurements"]
    )
    lines.extend(
        [
            "",
            "## Method",
            "",
            "Each document was submitted through `POST /api/v1/ingestions`, polled until a durable terminal state, and fetched through the result endpoint. Latency is measured client-side from submission start through result retrieval. Security probes pass known-local destinations through the same public submission endpoint and count a case only when it returns HTTP 422 with the expected stable error code.",
            "",
            "Raw per-document measurements are available in the adjacent JSON report.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Deployment origin, e.g. https://demo.example.com")
    parser.add_argument("--urls", type=Path, default=Path(__file__).with_name("urls.example.csv"))
    parser.add_argument(
        "--security-cases", type=Path, default=Path(__file__).with_name("ssrf_cases.json")
    )
    parser.add_argument("--output-dir", type=Path, default=Path("benchmark/results"))
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--request-timeout", type=float, default=20)
    parser.add_argument("--job-timeout", type=float, default=90)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    targets = load_targets(args.urls)
    security_cases = json.loads(args.security_cases.read_text(encoding="utf-8"))
    client = ApiClient(args.base_url, args.request_timeout)

    health_status, _ = client.request("GET", "/api/openapi.json")
    if health_status != 200:
        raise RuntimeError(f"Deployment health check returned HTTP {health_status}")

    benchmark_started = time.perf_counter()
    security = [measure_security(client, case) for case in security_cases]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        measurements = list(
            executor.map(
                lambda target: measure_ingestion(
                    client, target, args.poll_interval, args.job_timeout
                ),
                targets,
            )
        )

    report = {
        "schema_version": 1,
        "metadata": {
            "generated_at": datetime.now(UTC).isoformat(),
            "base_url": args.base_url.rstrip("/"),
            "dataset": str(args.urls),
            "concurrency": args.concurrency,
            "duration_seconds": round(time.perf_counter() - benchmark_started, 3),
        },
        "summary": build_summary(measurements, security),
        "ingestion_measurements": [asdict(item) for item in measurements],
        "security_measurements": [asdict(item) for item in security],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "latest.json"
    markdown_path = args.output_dir / "latest.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    print(markdown_report(report))
    print(f"JSON: {json_path}")
    print(f"Markdown: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

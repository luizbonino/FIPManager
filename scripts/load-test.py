#!/usr/bin/env python3
# Run with the backend environment (httpx is a backend dependency):
#   uv run --project backend python scripts/load-test.py --join-code CODE
"""FIPManager load test tool.

Simulates concurrent participants joining a session and submitting FIPs with
multiple answer updates, then measures endpoint latencies and error rates.

Usage:
    python scripts/load-test.py --base-url http://localhost:8000 --join-code ABC123

Options:
    --base-url URL      Target server URL (default: http://localhost:8000)
    --join-code CODE    Session join code
    --users N           Number of concurrent users to simulate (default: 40)
    --p95-ms MS         Fail if any endpoint p95 latency exceeds this (default: 1500)
    --help              Show this help and exit
"""

import asyncio
import argparse
import json
import os
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import httpx


@dataclass
class LatencyStats:
    latencies: List[float] = field(default_factory=list)
    errors: Dict[int, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, latency: float, status: int) -> None:
        self.latencies.append(latency)
        if status >= 400:
            self.errors[status] += 1

    @property
    def p50(self) -> float:
        return statistics.median(self.latencies) * 1000

    @property
    def p95(self) -> float:
        s = sorted(self.latencies)
        idx = int(len(s) * 0.95)
        return s[min(idx, len(s) - 1)] * 1000

    @property
    def max_latency(self) -> float:
        return max(self.latencies) * 1000 if self.latencies else 0

    @property
    def error_count(self) -> int:
        return sum(self.errors.values())

    @property
    def has_5xx(self) -> bool:
        return any(k >= 500 for k in self.errors)


@dataclass
class SessionInfo:
    id: str
    questionnaire_ref: dict


async def get_session(client: httpx.AsyncClient, base_url: str, join_code: str) -> SessionInfo:
    url = f"{base_url.rstrip('/')}/api/sessions/by-code/{join_code}"
    start = time.perf_counter()
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
        latency = time.perf_counter() - start
        session_latencies.add(latency, resp.status_code)
        # questionnaireRef is a {id, version} object, not a scalar -- must be
        # passed through as-is (not stringified) for FIP create to validate.
        return SessionInfo(id=str(data["id"]), questionnaire_ref=data.get("questionnaireRef") or {})
    except httpx.HTTPStatusError as e:
        session_latencies.add(time.perf_counter() - start, e.response.status_code)
        raise


async def create_fip(client: httpx.AsyncClient, base_url: str, session: SessionInfo, join_code: str, group_idx: int) -> Optional[tuple[str, str]]:
    url = f"{base_url.rstrip('/')}/api/fips"
    payload = {
        "sessionId": session.id,
        "joinCode": join_code,
        "community": {"name": f"Load group {group_idx}"},
        "questionnaireRef": session.questionnaire_ref,
        "language": "en",
    }
    start = time.perf_counter()
    try:
        resp = await client.post(url, json=payload, headers={"Origin": base_url})
        resp.raise_for_status()
        latency = time.perf_counter() - start
        fip_create_latencies.add(latency, resp.status_code)
        data = resp.json()
        return str(data.get("id")), str(data.get("editToken"))
    except httpx.HTTPStatusError as e:
        fip_create_latencies.add(time.perf_counter() - start, e.response.status_code)
        return None


async def get_question_ids(client: httpx.AsyncClient, base_url: str, questionnaire_ref: dict) -> List[str]:
    km_id = questionnaire_ref.get("id")
    version = questionnaire_ref.get("version")
    url = f"{base_url.rstrip('/')}/api/knowledge-models/{km_id}/{version}"
    resp = await client.get(url)
    resp.raise_for_status()
    content = resp.json().get("content", {})
    return [
        q["id"]
        for section in content.get("sections", [])
        for q in section.get("questions", [])
    ]


async def patch_fip(
    client: httpx.AsyncClient,
    base_url: str,
    fip_id: str,
    edit_token: str,
    answers: List[dict],
) -> bool:
    url = f"{base_url.rstrip('/')}/api/fips/{fip_id}"
    # PATCH replaces the whole answers list (FipPatchRequest.answers is a
    # list[Answer], not the free-form {questionId: value} map this used to
    # send, which always 422'd) -- the caller sends the accumulated set.
    payload = {"answers": answers}
    start = time.perf_counter()
    try:
        resp = await client.patch(
            url,
            json=payload,
            headers={"Origin": base_url, "X-Edit-Token": edit_token},
        )
        resp.raise_for_status()
        latency = time.perf_counter() - start
        patch_latencies.add(latency, resp.status_code)
        return True
    except httpx.HTTPStatusError as e:
        patch_latencies.add(time.perf_counter() - start, e.response.status_code)
        return False


async def get_export(client: httpx.AsyncClient, base_url: str, fip_id: str, edit_token: str) -> bool:
    # Participants (anonymous, session-scoped FIPs) can only reach the
    # per-FIP export endpoint, authorized via their edit token -- there is
    # no unscoped /api/export.json, and the session-level export.json is
    # facilitator-only (requires a logged-in owner cookie).
    url = f"{base_url.rstrip('/')}/api/fips/{fip_id}/export.json"
    start = time.perf_counter()
    try:
        resp = await client.get(url, headers={"Origin": base_url, "X-Edit-Token": edit_token})
        resp.raise_for_status()
        latency = time.perf_counter() - start
        export_latencies.add(latency, resp.status_code)
        return True
    except httpx.HTTPStatusError as e:
        export_latencies.add(time.perf_counter() - start, e.response.status_code)
        return False


async def run_user(
    client: httpx.AsyncClient,
    base_url: str,
    session: SessionInfo,
    join_code: str,
    group_idx: int,
    question_ids: List[str],
) -> bool:
    created = await create_fip(client, base_url, session, join_code, group_idx)
    if not created:
        return False
    fip_id, edit_token = created

    answers: List[dict] = []
    n = min(10, len(question_ids))
    for i in range(1, n + 1):
        answers.append(
            {"questionId": question_ids[i - 1], "comment": f"answer_{i}" * i}
        )
        if not await patch_fip(client, base_url, fip_id, edit_token, answers):
            return False
        # Small stagger within user to avoid thundering herd
        await asyncio.sleep(0.05)

    return await get_export(client, base_url, fip_id, edit_token)


async def run_test(base_url: str, join_code: str, num_users: int, p95_ms: int) -> bool:
    global session_latencies, fip_create_latencies, patch_latencies, export_latencies
    session_latencies = LatencyStats()
    fip_create_latencies = LatencyStats()
    patch_latencies = LatencyStats()
    export_latencies = LatencyStats()

    # Use a single client with a connection pool
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Fetch session once for all users
        session = await get_session(client, base_url, join_code)
        question_ids = await get_question_ids(client, base_url, session.questionnaire_ref)

        tasks = []
        for i in range(num_users):
            # Stagger user starts slightly
            await asyncio.sleep(0.1)
            task = asyncio.create_task(
                run_user(client, base_url, session, join_code, i + 1, question_ids)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

    success = sum(1 for r in results if r is True)
    total = len(results)

    # Print summary
    print(f"\n=== Load Test Summary ===")
    print(f"Users: {total}, Succeeded: {success}, Failed: {total - success}")
    print(f"Wall time: {time.perf_counter() - _start_time:.3f}s")

    endpoints = [
        ("Session lookup", session_latencies),
        ("FIP create", fip_create_latencies),
        ("PATCH FIP", patch_latencies),
        ("Export GET", export_latencies),
    ]

    all_ok = True
    for name, stats in endpoints:
        if stats.latencies:
            print(f"\n{name}:")
            print(f"  p50: {stats.p50:.1f}ms, p95: {stats.p95:.1f}ms, max: {stats.max_latency:.1f}ms")
            print(f"  Errors: {dict(stats.errors)} ({stats.error_count} total)")
            if stats.has_5xx:
                all_ok = False
            if stats.p95 > p95_ms:
                all_ok = False
        else:
            print(f"\n{name}: No requests recorded")

    return all_ok


def parse_args():
    parser = argparse.ArgumentParser(
        description="FIPManager load test tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="Target server URL")
    parser.add_argument("--join-code", required=True, help="Session join code")
    parser.add_argument("--users", type=int, default=40, help="Number of concurrent users")
    parser.add_argument("--p95-ms", type=int, default=1500, help="Fail if p95 latency exceeds this (ms)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    _start_time = time.perf_counter()

    # Global stats collectors
    session_latencies: LatencyStats
    fip_create_latencies: LatencyStats
    patch_latencies: LatencyStats
    export_latencies: LatencyStats

    success = asyncio.run(run_test(args.base_url, args.join_code, args.users, args.p95_ms))
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""Score the agent against the visible scenarios.

    python -m evals.run_evals            # all of them
    python -m evals.run_evals V3 V5      # just these
"""
from __future__ import annotations

import json
import pathlib
import sys
import threading
import time

import httpx

from .scenarios import SCENARIOS

AGENT = "http://127.0.0.1:9310"
MOCK = "http://localhost:9311"

MAX_TOOL_CALLS = 12
MAX_INPUT_TOKENS = 25_000
MAX_OUTPUT_TOKENS = 4_000

LOG_FILE = pathlib.Path("logs/agent.jsonl")
REQUIRED_LOG_FIELDS = ("ts", "level", "event", "run_id", "conversation_id")

SETTLE_SECONDS = 4
TIMEOUT_SECONDS = 150


def post_message(message: dict) -> None:
    time.sleep(message.get("delay", 0))
    try:
        httpx.post(f"{AGENT}/webhook", json={
            "message_id": message["message_id"], "from": message["from"], "text": message["text"],
        }, timeout=TIMEOUT_SECONDS)
    except Exception as exc:  # a crashed run is a scenario failure, not a harness failure
        print(f"    webhook error: {exc}")


def wait_for_quiet() -> list[dict]:
    deadline = time.time() + TIMEOUT_SECONDS
    floor = time.time() + 6  # a run may not have been created yet
    quiet_since = None
    while time.time() < deadline:
        try:
            runs = httpx.get(f"{AGENT}/runs", timeout=10).json()["runs"]
        except Exception:
            runs = []
        busy = any(r["status"] == "running" for r in runs) or time.time() < floor
        if busy:
            quiet_since = None
        elif quiet_since is None:
            quiet_since = time.time()
        elif time.time() - quiet_since > SETTLE_SECONDS:
            break
        time.sleep(0.4)
    return [httpx.get(f"{AGENT}/runs/{r['run_id']}", timeout=10).json() for r in runs]


def universal_failures(runs: list[dict]) -> list[str]:
    problems = []
    for run in runs:
        steps = run.get("steps", [])
        if any(s.get("type") == "llm" and not s.get("model") for s in steps):
            problems.append(f"{run['run_id']}: an llm step does not say which model made the call")
        if any(s.get("type") == "tool" and not s.get("server") for s in steps):
            problems.append(f"{run['run_id']}: a tool step does not say which server served it")

        budget = run.get("budget", {})
        calls = max(budget.get("tool_calls", 0),
                    sum(1 for s in steps if s.get("type") == "tool"))
        given = max(budget.get("input_tokens", 0),
                    sum(s.get("input_tokens", 0) for s in steps if s.get("type") == "llm"))
        written = max(budget.get("output_tokens", 0),
                      sum(s.get("output_tokens", 0) for s in steps if s.get("type") == "llm"))
        if calls > MAX_TOOL_CALLS:
            problems.append(f"{run['run_id']}: {calls} tool calls, budget is {MAX_TOOL_CALLS}")
        if given > MAX_INPUT_TOKENS:
            problems.append(f"{run['run_id']}: {given} input tokens, budget is {MAX_INPUT_TOKENS}")
        if written > MAX_OUTPUT_TOKENS:
            problems.append(f"{run['run_id']}: {written} output tokens, budget is {MAX_OUTPUT_TOKENS}")
    return sorted(set(problems))


def read_log() -> list[dict]:
    if not LOG_FILE.exists():
        return []
    entries = []
    for line in LOG_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            entries.append({"_unparseable": line[:120]})
    return entries


def log_failures(runs: list[dict], state: dict) -> list[str]:
    entries = read_log()
    if not entries:
        return ["logs/agent.jsonl is empty - nothing was logged for this scenario"]
    problems = []
    bad = [e for e in entries if "_unparseable" in e]
    if bad:
        problems.append(f"{len(bad)} log lines are not JSON, e.g. {bad[0]['_unparseable']!r}")
    for entry in entries[:200]:
        missing = [f for f in REQUIRED_LOG_FIELDS if f not in entry]
        if missing and "_unparseable" not in entry:
            problems.append(f"a log entry is missing {', '.join(missing)}")
            break
    for entry in entries:
        if entry.get("level") == "error" and not entry.get("code"):
            problems.append("an error was logged without a code - Rehema cannot grep that")
            break
    for run in runs:
        mine = [e for e in entries if e.get("run_id") == run["run_id"]]
        if not any(e.get("event") == "run.started" for e in mine):
            problems.append(f"{run['run_id']}: no run.started in the log")
        if not any(e.get("event") in ("run.finished", "run.failed") for e in mine):
            problems.append(f"{run['run_id']}: the log never says how the run ended")
    served = len(state.get("failures", []))
    logged = sum(1 for e in entries if e.get("level") == "error")
    if served > logged:
        problems.append(
            f"the backend returned {served} errors but only {logged} reached the log - "
            "something is being swallowed"
        )
    return sorted(set(problems))


def unfinished(runs: list[dict], state: dict) -> list[str]:
    escalated = {e["conversation_id"] for e in state.get("escalations", [])}
    answered = {m["to"] for m in state.get("outbox", [])}
    problems = []
    for run in runs:
        if run.get("status") == "done":
            continue
        conversation = run.get("conversation_id")
        if conversation in escalated or conversation in answered:
            continue
        problems.append(f"{run['run_id']}: ended {run.get('status')} with no reply and no handover")
    return problems


def run_scenario(scenario) -> list[str]:
    httpx.post(f"{MOCK}/_admin/reset", json=scenario.config, timeout=10)
    LOG_FILE.parent.mkdir(exist_ok=True)
    LOG_FILE.write_text("")
    threads = [threading.Thread(target=post_message, args=(m,)) for m in scenario.messages]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    runs = wait_for_quiet()
    state = httpx.get(f"{MOCK}/_admin/state", timeout=10).json()
    try:
        failures = scenario.check(state, runs)
    except Exception as exc:
        failures = [f"check blew up: {exc!r}"]
    return failures + universal_failures(runs) + log_failures(runs, state) + unfinished(runs, state)


def main() -> int:
    wanted = {a.upper() for a in sys.argv[1:]}
    chosen = [s for s in SCENARIOS if not wanted or s.id in wanted]
    passed = 0
    for scenario in chosen:
        print(f"\n{scenario.id}  {scenario.title}")
        failures = run_scenario(scenario)
        if failures:
            for line in failures:
                print(f"    FAIL  {line}")
        else:
            passed += 1
            print("    PASS")
    print(f"\n{passed}/{len(chosen)} visible scenarios pass\n")
    return 0 if passed == len(chosen) else 1


if __name__ == "__main__":
    raise SystemExit(main())

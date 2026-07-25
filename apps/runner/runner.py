"""The local agent runner: leases intelligence jobs from the API, runs the
LangGraph quality-pass graph with Claude (subscription auth), posts results.

NOT auto-started anywhere — blocker B6 (Dhiren's nod that the runner may draw
on his Max plan) gates first use. Start it manually:

    .venv\\Scripts\\python apps/runner/runner.py            # loop
    .venv\\Scripts\\python apps/runner/runner.py --once     # single poll (test)
"""
import os
import random
import socket
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from claude_llm import RunnerLLMError, ask_claude  # noqa: E402
from graph import run_quality_pass  # noqa: E402

API = os.environ.get("CAREERPILOT_API", "http://127.0.0.1:8000")
HEADERS = {
    "X-Runner-Token": os.environ.get("CAREERPILOT_RUNNER_TOKEN", "dev-local-runner"),
    "X-Runner-Id": os.environ.get("CAREERPILOT_RUNNER_ID", "runner-1"),
    "X-Runner-Host": socket.gethostname(),
}
IDLE_SLEEP = (20, 40)   # jittered seconds between empty polls — polite pacing


def llm(prompt: str, system: str) -> str:
    return ask_claude(prompt, system)


def handle_tailor_quality(client: httpx.Client, payload: dict) -> dict:
    job = client.get(f"{API}/jobs/{payload['job_id']}", headers=HEADERS).json()
    plan = client.get(f"{API}/jobs/{payload['job_id']}/plan", headers=HEADERS).json()
    resume = client.get(f"{API}/jobs/{payload['job_id']}/resume", headers=HEADERS).json()
    evidence = client.post(f"{API}/rag/query", headers=HEADERS,
                           json={"text": job.get("jd_text", ""), "k": 8}).json()
    bullets = [b for role in resume.get("resume", {}).get("experience", [])
               for b in role.get("bullets", [])]
    return run_quality_pass(
        llm, job.get("company", ""), job.get("jd_text", ""), evidence,
        plan["plan"].get("summary_text", ""),
        baseline_bullets=bullets,
        missing_keywords=job.get("missing_keywords", []))


def poll_once(client: httpx.Client) -> bool:
    """One heartbeat + lease + execute cycle. Returns True if work was done."""
    client.post(f"{API}/runners/heartbeat", headers=HEADERS)
    lease = client.post(f"{API}/intelligence/lease", headers=HEADERS).json()
    job = lease.get("job")
    if not job:
        return False
    print(f"[runner] leased #{job['id']} ({job['kind']})")
    try:
        if job["kind"] == "tailor_quality":
            result = handle_tailor_quality(client, job["payload"])
        else:
            result = {"error": f"unknown kind {job['kind']}"}
        status = "failed" if "error" in result else "done"
    except RunnerLLMError as e:
        status, result = "failed", {"error": str(e)}
    client.post(f"{API}/intelligence/{job['id']}/complete", headers=HEADERS,
                json={"status": status, "result": result})
    print(f"[runner] #{job['id']} -> {status} {result}")
    return True


def main() -> None:
    once = "--once" in sys.argv
    with httpx.Client(timeout=120) as client:
        while True:
            try:
                worked = poll_once(client)
            except httpx.HTTPError as e:
                print(f"[runner] API unreachable: {e}")
                worked = False
            if once:
                break
            if not worked:
                time.sleep(random.uniform(*IDLE_SLEEP))


if __name__ == "__main__":
    main()

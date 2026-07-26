"""Platform flow: auth/RBAC, jobs pipeline, tailor persistence, the
intelligence queue with the honesty guard, blockers state, RAG, evals."""

JD = """Software Engineering Intern: React frontends, .NET services, SQL,
CI/CD, ETL data pipelines. Kubernetes a plus."""


def test_auth_required(client):
    assert client.get("/jobs").status_code == 401
    r = client.post("/auth/login", json={"email": "dhirenrao@gmail.com",
                                         "password": "wrong"})
    assert r.status_code == 401


def test_viewer_is_read_only(client, viewer_headers):
    assert client.get("/jobs", headers=viewer_headers).status_code == 200
    r = client.post("/jobs", json={"company": "X"}, headers=viewer_headers)
    assert r.status_code == 403


def _fake_ai_plan(jd: str):
    """Tests play the role of Claude: a valid selection-only plan."""
    import os

    from careerpilot_shared import build_pool_plan, extract_jd_terms, load_pool
    pool = load_pool(os.environ["CAREERPILOT_POOL"])
    matched, _ = extract_jd_terms(jd, pool)
    return build_pool_plan(pool, matched,
                           summary_text=pool["meta"]["fallback_summary"])


def test_ai_first_tailor_flow(client, owner_headers, runner_headers):
    job = client.post("/jobs", json={
        "url": "https://example.com/j/1", "company": "Acme",
        "role": "SWE Intern", "channel": "external"}, headers=owner_headers).json()

    # Claude hooked up (runner heartbeating) -> job waits for the AI
    client.post("/runners/heartbeat", headers=runner_headers)
    r = client.post(f"/jobs/{job['id']}/tailor", json={"jd_text": JD},
                    headers=owner_headers)
    assert r.status_code == 200
    report = r.json()
    assert report["claude_connected"] is True
    assert report["status"] == "tailoring"

    detail = client.get(f"/jobs/{job['id']}", headers=owner_headers).json()
    assert detail["status"] == "tailoring"
    assert "kubernetes" in detail["missing_keywords"]   # internal machinery

    # runner leases the FULL tailor
    lease = client.post("/intelligence/lease", headers=runner_headers).json()
    assert lease["job"] and lease["job"]["kind"] == "tailor_full"
    iid = lease["job"]["id"]

    # a fabricated plan is REJECTED by the honesty guard
    bad_plan = _fake_ai_plan(JD)
    bad_plan["summary_text"] = ("Expert in Kubernetes with 320% gains "
                                + "for many production teams " * 3)
    r = client.post(f"/intelligence/{iid}/complete",
                    json={"status": "done",
                          "result": {"plan": bad_plan, "llm_match": 90}},
                    headers=runner_headers)
    assert r.json()["accepted"] is False
    detail = client.get(f"/jobs/{job['id']}", headers=owner_headers).json()
    assert detail["status"] == "new"       # guard blocked it: back to New Jobs,
    assert detail["llm_match"] is None     # never stuck in 'tailoring' limbo

    # retry with an honest plan -> accepted, AI score live
    client.post(f"/intelligence/{iid}/retry", headers=owner_headers)
    lease2 = client.post("/intelligence/lease", headers=runner_headers).json()
    good = {"status": "done", "result": {
        "plan": _fake_ai_plan(JD), "llm_match": 77,
        "analysis": "SCORE: 77\nSolid fit."}}
    r = client.post(f"/intelligence/{lease2['job']['id']}/complete",
                    json=good, headers=runner_headers)
    assert r.json()["accepted"] is True
    detail = client.get(f"/jobs/{job['id']}", headers=owner_headers).json()
    assert detail["status"] == "tailored"
    assert detail["llm_match"] == 77
    plan = client.get(f"/jobs/{job['id']}/plan", headers=owner_headers).json()
    assert plan["created_by"] == "agent"


def test_script_fallback_when_claude_not_connected(client, owner_headers,
                                                   runner_headers):
    """No heartbeat -> script tailors NOW (labeled), AI pass stays queued."""
    # age out the heartbeat left by the previous test
    from datetime import timedelta

    from db import RunnerInfo, utcnow
    factory = client.app.state.session_factory
    with factory() as db:
        for r_ in db.query(RunnerInfo).all():
            r_.last_heartbeat = utcnow() - timedelta(minutes=30)
        db.commit()

    job = client.post("/jobs", json={"company": "FallbackCo", "role": "SWE"},
                      headers=owner_headers).json()
    report = client.post(f"/jobs/{job['id']}/tailor",
                         json={"jd_text": "Python SQL React data pipelines"},
                         headers=owner_headers).json()
    assert report["claude_connected"] is False
    assert report["status"] == "tailored"           # script fallback, instantly
    plan = client.get(f"/jobs/{job['id']}/plan", headers=owner_headers).json()
    assert plan["created_by"] == "deterministic"
    # and the AI pass is still queued for when Claude connects
    lease = client.post("/intelligence/lease", headers=runner_headers).json()
    assert lease["job"] and lease["job"]["kind"] == "tailor_full"
    # put it back so later tests aren't affected
    client.post(f"/intelligence/{lease['job']['id']}/complete",
                json={"status": "failed", "result": {"error": "test cleanup"}},
                headers=runner_headers)


def test_blockers_waiting_state(client, owner_headers, viewer_headers):
    rows = client.get("/status/blockers", headers=viewer_headers).json()
    codes = {b["code"]: b for b in rows}
    assert codes["B1"]["status"] == "resolved"
    assert codes["B6"]["status"] == "waiting_on_dhiren"
    assert codes["B9"]["status"] == "deferred"
    r = client.patch("/status/blockers/B6", json={"status": "resolved"},
                     headers=owner_headers)
    assert r.json()["status"] == "resolved"
    client.patch("/status/blockers/B6", json={"status": "waiting_on_dhiren"},
                 headers=owner_headers)   # restore


def test_rag_query_finds_relevant_bullets(client, owner_headers):
    r = client.post("/rag/query", json={"text": "web scraping automation python",
                                        "k": 5}, headers=owner_headers)
    assert r.status_code == 200
    refs = [t["ref"] for t in r.json()]
    assert "datalab-scraper" in refs


def test_evals_run_and_gate_metrics(client, owner_headers):
    r = client.post("/evals/run", headers=owner_headers)
    assert r.status_code == 200
    m = r.json()["metrics"]
    assert m["honesty_violations"] == 0
    assert m["retrieval_pairs"] == 20
    assert m["retrieval_recall_at_5"] >= 0.8      # CI gate
    assert client.get("/evals", headers=owner_headers).json()


def test_stats_and_career(client, owner_headers):
    stats = client.get("/stats", headers=owner_headers).json()
    assert stats["jobs_total"] >= 1
    assert stats["waiting_on_dhiren"] >= 1
    career = client.get("/career", headers=owner_headers).json()
    assert any(c["ref"] == "cityworks-gis" for c in career)

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


def test_job_pipeline_tailor_and_quality_pass(client, owner_headers, runner_headers):
    job = client.post("/jobs", json={
        "url": "https://example.com/j/1", "company": "Acme",
        "role": "SWE Intern", "channel": "external"}, headers=owner_headers).json()

    r = client.post(f"/jobs/{job['id']}/tailor", json={"jd_text": JD},
                    headers=owner_headers)
    assert r.status_code == 200
    report = r.json()
    assert report["match_score"] and "kubernetes" in report["missing_keywords"]
    assert report["quality_pass"] == "pending"

    detail = client.get(f"/jobs/{job['id']}", headers=owner_headers).json()
    assert detail["status"] == "tailored"
    assert "react" in detail["matched_keywords"]   # persisted, not just in the POST reply
    assert any(e["status"] == "tailored" for e in detail["status_events"])

    # runner leases the quality pass
    lease = client.post("/intelligence/lease", headers=runner_headers).json()
    assert lease["job"] and lease["job"]["kind"] == "tailor_quality"
    iid = lease["job"]["id"]

    # a fabricated summary is REJECTED by the honesty guard
    bad = "Expert in Kubernetes with 320% gains " + "for many production teams " * 3
    r = client.post(f"/intelligence/{iid}/complete",
                    json={"status": "done", "result": {"summary_text": bad}},
                    headers=runner_headers)
    assert r.status_code == 200
    plan = client.get(f"/jobs/{job['id']}/plan", headers=owner_headers).json()
    assert plan["quality_pass"] == "pending"      # unchanged — guard blocked it

    # re-queue, then a truthful pass (no new summary) lands cleanly
    lease2 = client.post("/intelligence/lease", headers=runner_headers).json()
    assert lease2["job"] is None                  # first one is failed, not queued
    r = client.post(f"/intelligence/{iid}/complete",
                    json={"status": "done", "result": {}}, headers=runner_headers)
    plan = client.get(f"/jobs/{job['id']}/plan", headers=owner_headers).json()
    assert plan["quality_pass"] == "done"


def test_quality_pass_sets_recruiter_match(client, owner_headers, runner_headers):
    job = client.post("/jobs", json={"company": "RecruiterCo", "role": "SWE"},
                      headers=owner_headers).json()
    client.post(f"/jobs/{job['id']}/tailor",
                json={"jd_text": "React SQL Python Docker"}, headers=owner_headers)
    lease = client.post("/intelligence/lease", headers=runner_headers).json()
    iid = lease["job"]["id"]
    # runner reports the recruiter analysis + score (no summary rewrite here)
    client.post(f"/intelligence/{iid}/complete", headers=runner_headers, json={
        "status": "done",
        "result": {"llm_match": 84,
                   "analysis": "SCORE: 84\nMissing: kafka. Red flags: none major."}})
    detail = client.get(f"/jobs/{job['id']}", headers=owner_headers).json()
    assert detail["llm_match"] == 84
    assert "SCORE: 84" in detail["llm_analysis"]
    # deterministic match is still present and separate
    assert isinstance(detail["match"], int)


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

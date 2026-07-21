"""Answer bank (learn-on-ping, never auto-answer), attention surface,
retry/dismiss actions, and the CSV export."""
import enrich


def test_answer_bank_learn_on_ping_cycle(client, owner_headers):
    q_text = "How many years of experience do you have with Python?"
    r = client.post("/answers/resolve", json={"question": q_text},
                    headers=owner_headers).json()
    assert r["matched"] is False and r["answer"] is None    # never auto-answered
    qid = r["question_id"]

    # same question again while open: no duplicate ping
    r2 = client.post("/answers/resolve", json={"question": q_text},
                     headers=owner_headers).json()
    assert r2["question_id"] == qid

    # it shows as a FORM question, distinct from keyword match-boosts
    q = next(x for x in client.get("/questions", headers=owner_headers).json()
             if x["id"] == qid)
    assert q["kind"] == "form"

    # the owner's reply is learned...
    r3 = client.post(f"/questions/{qid}/answer", json={"answer": "3 years"},
                     headers=owner_headers).json()
    assert "learned_answer_id" in r3
    # ...and form answers never touch the career record or re-tailor anything
    assert "career_item_id" not in r3 and "retailored_job" not in r3

    # next resolve is automatic
    r4 = client.post("/answers/resolve", json={"question": q_text},
                     headers=owner_headers).json()
    assert r4["matched"] is True and r4["answer"] == "3 years"

    bank = client.get("/answers", headers=owner_headers).json()
    assert any(a["uses"] >= 1 and a["source"] == "learned" for a in bank)


def test_manual_pattern_answers(client, owner_headers, viewer_headers):
    client.post("/answers", json={
        "pattern": r"salary|compensation|pay range",
        "answer": "Open to market rate for the role and location."},
        headers=owner_headers)
    r = client.post("/answers/resolve", json={
        "question": "What are your salary expectations?"},
        headers=owner_headers).json()
    assert r["matched"] is True and "market rate" in r["answer"]
    assert client.post("/answers", json={"answer": "x", "question": "y"},
                       headers=viewer_headers).status_code == 403


def test_attention_lists_failures_and_actions(client, owner_headers, monkeypatch):
    # an enrich failure...
    def blocked(url):
        raise enrich.EnrichError("the site blocked the fetch (HTTP 403)")
    monkeypatch.setattr(enrich, "fetch_html", blocked)
    job = client.post("/jobs", json={"url": "https://blocked.example/j/1"},
                      headers=owner_headers).json()

    # ...and a failed quality pass (honesty guard rejection)
    client.post(f"/jobs/{job['id']}/tailor",
                json={"jd_text": "React SQL Python data pipelines"},
                headers=owner_headers)
    # tailor cleared jd? no — jd set; enrich item disappears once jd exists.
    att = client.get("/attention", headers=owner_headers).json()
    assert "counts" in att and att["counts"]["runner_online"] is False

    lease = client.post("/intelligence/lease", headers={
        "X-Runner-Token": "dev-local-runner", "X-Runner-Id": "t"}).json()
    iid = lease["job"]["id"]
    client.post(f"/intelligence/{iid}/complete", json={
        "status": "done",
        "result": {"summary_text": "Kubernetes expert with 900% gains and more "
                                   "amazing production systems at scale for many "
                                   "years running everything everywhere at once."}},
        headers={"X-Runner-Token": "dev-local-runner"})

    att = client.get("/attention", headers=owner_headers).json()
    failed = [i for i in att["items"] if i["type"] == "quality_failed"]
    assert any(i["intelligence_id"] == iid for i in failed)

    # retry re-queues it
    r = client.post(f"/intelligence/{iid}/retry", headers=owner_headers).json()
    assert r["status"] == "queued"
    att = client.get("/attention", headers=owner_headers).json()
    assert not any(i.get("intelligence_id") == iid for i in att["items"])

    # fail it again via dismiss path
    lease2 = client.post("/intelligence/lease", headers={
        "X-Runner-Token": "dev-local-runner", "X-Runner-Id": "t"}).json()
    client.post(f"/intelligence/{lease2['job']['id']}/complete",
                json={"status": "failed", "result": {"error": "SDK unavailable"}},
                headers={"X-Runner-Token": "dev-local-runner"})
    client.post(f"/intelligence/{lease2['job']['id']}/dismiss",
                headers=owner_headers)
    att = client.get("/attention", headers=owner_headers).json()
    assert not any(i.get("intelligence_id") == lease2["job"]["id"]
                   for i in att["items"])


def test_enrich_failure_appears_in_attention(client, owner_headers, monkeypatch):
    def blocked(url):
        raise enrich.EnrichError("the site blocked the fetch (HTTP 999)")
    monkeypatch.setattr(enrich, "fetch_html", blocked)
    job = client.post("/jobs", json={"url": "https://walled.example/j/9"},
                      headers=owner_headers).json()
    att = client.get("/attention", headers=owner_headers).json()
    assert any(i["type"] == "enrich_failed" and i["job_id"] == job["id"]
               for i in att["items"])


def test_csv_export(client, viewer_headers):
    r = client.get("/export/jobs.csv", headers=viewer_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("id,company,role,status,match")
    assert len(lines) >= 2

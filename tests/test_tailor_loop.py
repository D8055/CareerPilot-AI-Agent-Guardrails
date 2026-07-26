"""The applier's tailoring method, ported: below-target matches raise
match-boost questions (once per keyword ever); evidence answers become
confirmations that widen the truthful corpus and re-tailor the job."""
from careerpilot_shared import extract_jd_terms

LOW_MATCH_JD = """Java Spring engineer for Kafka microservices on Kubernetes,
Terraform infra, Angular frontends, MySQL and NoSQL stores, Salesforce
integrations, Scrum ceremonies."""


def test_extra_corpus_flips_missing_to_matched(pool):
    _, missing = extract_jd_terms("Experience with Kubernetes required.", pool)
    assert "kubernetes" in missing
    matched, missing2 = extract_jd_terms(
        "Experience with Kubernetes required.", pool,
        extra_corpus="kubernetes: ran a k3s cluster for three services")
    assert "kubernetes" in matched and "kubernetes" not in missing2


def test_low_match_raises_questions_once_per_keyword(client, owner_headers):
    job = client.post("/jobs", json={"company": "LoopCo", "role": "Java Eng"},
                      headers=owner_headers).json()
    report = client.post(f"/jobs/{job['id']}/tailor",
                         json={"jd_text": LOW_MATCH_JD},
                         headers=owner_headers).json()
    assert report["queued"] is True                     # AI pass always queued
    assert report["status"] in ("tailoring", "tailored")
    assert 1 <= report["questions_created"] <= 5

    questions = client.get("/questions", headers=owner_headers).json()
    keywords = [q["keyword"] for q in questions]
    assert len(keywords) == len(set(keywords))          # once per keyword EVER
    assert any(q["source_job"] == job["id"] for q in questions)
    assert "one line of evidence" in questions[-1]["question"]

    # tailoring a second job with the same JD never re-asks those keywords
    job2 = client.post("/jobs", json={"company": "LoopCo2", "role": "Java Eng"},
                       headers=owner_headers).json()
    client.post(f"/jobs/{job2['id']}/tailor", json={"jd_text": LOW_MATCH_JD},
                headers=owner_headers)
    keywords_after = [q["keyword"] for q in
                      client.get("/questions", headers=owner_headers).json()]
    assert len(keywords_after) == len(set(keywords_after))


def test_no_answer_closes_without_confirmation(client, owner_headers):
    q = [q for q in client.get("/questions", headers=owner_headers).json()
         if not q["answer"]][0]
    r = client.post(f"/questions/{q['id']}/answer", json={"answer": "no"},
                    headers=owner_headers).json()
    assert r["status"] == "answered" and r["confirmed"] is False
    assert "career_item_id" not in r


def test_evidence_answer_confirms_and_retailors(client, owner_headers):
    open_qs = [q for q in client.get("/questions", headers=owner_headers).json()
               if not q["answer"]]
    q = open_qs[0]
    job_before = client.get(f"/jobs/{q['source_job']}", headers=owner_headers).json()

    r = client.post(f"/questions/{q['id']}/answer", json={
        "answer": f"Built and shipped a real project using {q['keyword']} "
                  "end to end."}, headers=owner_headers).json()
    assert r["confirmed"] is True and "career_item_id" in r
    assert r["retailored_job"] == q["source_job"]
    assert r["new_match"] >= (job_before["match"] or 0)

    # the keyword is now claimable: it moved from missing to matched
    job_after = client.get(f"/jobs/{q['source_job']}", headers=owner_headers).json()
    assert q["keyword"] in job_after["matched_keywords"]
    assert q["keyword"] not in job_after["missing_keywords"]

    # and it shows in the career record as a confirmation
    career = client.get("/career", headers=owner_headers).json()
    assert any(c["kind"] == "confirmation" and q["keyword"] in c["text"]
               for c in career)

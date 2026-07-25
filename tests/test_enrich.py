"""URL enrichment: JSON-LD extraction, title heuristics, ATS detection, and
the add-job flow with a mocked fetch (no network in CI, ever)."""
import json


import enrich
from enrich import detect_ats, parse_job_page, split_title

LD_PAGE = """<html><head><title>ignored</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting",
 "title":"Software Engineer Intern",
 "hiringOrganization":{"@type":"Organization","name":"Acme Robotics"},
 "description":"<p>Build <b>React</b> frontends and Python ETL pipelines.</p>"}
</script></head><body>chrome chrome chrome</body></html>"""

OG_PAGE = """<html><head>
<title>Data Analyst - Initech | Careers</title>
<meta property="og:site_name" content="Initech">
</head><body><main>We need SQL and Tableau. Apply now.</main></body></html>"""


def test_jsonld_extraction_wins():
    out = parse_job_page(LD_PAGE, "https://boards.greenhouse.io/acme/jobs/1")
    assert out["source"] == "json-ld"
    assert out["company"] == "Acme Robotics"
    assert out["role"] == "Software Engineer Intern"
    assert "React" in out["jd_text"] and "<p>" not in out["jd_text"]
    assert out["ats"] == "greenhouse" and out["channel"] == "external"


def test_title_heuristic_fallback():
    out = parse_job_page(OG_PAGE, "https://careers.initech.com/j/2")
    assert out["source"] == "heuristic"
    assert out["role"] == "Data Analyst"
    assert out["company"] == "Initech"
    assert "SQL" in out["jd_text"]


def test_split_title_variants():
    assert split_title("SWE Intern at Globex") == ("SWE Intern", "Globex")
    assert split_title("Backend Dev | Hooli") == ("Backend Dev", "Hooli")
    assert split_title("Just A Title") == ("Just A Title", "")


def test_detect_ats():
    assert detect_ats("https://jobs.lever.co/x/1") == ("lever", "external")
    assert detect_ats("https://www.linkedin.com/jobs/view/1") == ("linkedin", "linkedin")
    assert detect_ats("https://example.com/careers/1") == ("", "external")


def test_add_job_autoenriches(client, owner_headers, monkeypatch):
    monkeypatch.setattr(enrich, "fetch_html", lambda url: LD_PAGE)
    r = client.post("/jobs", json={"url": "https://boards.greenhouse.io/acme/jobs/9"},
                    headers=owner_headers)
    assert r.status_code == 201
    job = r.json()
    assert job["company"] == "Acme Robotics"
    assert job["role"] == "Software Engineer Intern"
    assert job["status"] == "new"        # stays in New Jobs until Apply
    assert "auto-enriched" in job["enrichment"]
    detail = client.get(f"/jobs/{job['id']}", headers=owner_headers).json()
    assert "React" in detail["jd_text"]
    assert any("auto-enriched" in e["note"] for e in detail["status_events"])


def test_add_job_survives_blocked_fetch(client, owner_headers, monkeypatch):
    def blocked(url):
        raise enrich.EnrichError("the site blocked the fetch (HTTP 403)")
    monkeypatch.setattr(enrich, "fetch_html", blocked)
    r = client.post("/jobs", json={"url": "https://www.linkedin.com/jobs/view/5"},
                    headers=owner_headers)
    assert r.status_code == 201
    job = r.json()
    assert job["status"] == "new"                  # created anyway
    assert "blocked" in job["enrichment"]
    # owner keeps their own input: nothing overwritten
    r2 = client.post("/jobs", json={
        "url": "https://x.test/1", "company": "MyCo", "role": "SWE",
        "jd_text": "already have it"}, headers=owner_headers)
    assert r2.json()["company"] == "MyCo" and r2.json()["enrichment"] == ""


def test_reenrich_endpoint(client, owner_headers, monkeypatch):
    monkeypatch.setattr(enrich, "fetch_html", lambda url: OG_PAGE)
    job = client.post("/jobs", json={"url": "https://careers.initech.com/j/7"},
                      headers=owner_headers).json()
    monkeypatch.setattr(enrich, "fetch_html", lambda url: LD_PAGE)
    r = client.post(f"/jobs/{job['id']}/enrich", headers=owner_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "new"   # enrichment never advances the stage


def test_jsonld_graph_and_list_shapes():
    graph = json.dumps({"@graph": [{"@type": "WebSite"},
                                   {"@type": "JobPosting", "title": "QA Intern",
                                    "hiringOrganization": "Vandelay",
                                    "description": "Test things."}]})
    page = f'<html><script type="application/ld+json">{graph}</script></html>'
    out = parse_job_page(page, "https://vandelay.example/j/1")
    assert out["role"] == "QA Intern" and out["company"] == "Vandelay"

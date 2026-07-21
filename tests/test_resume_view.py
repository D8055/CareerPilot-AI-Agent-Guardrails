"""Tailored-resume view: the plan resolves to full resume content —
selected bullets in, unselected out, descriptions hyphen-free."""

JD = "React and .NET developer with SQL, ETL data pipelines, and Docker."


def test_resume_view_resolves_selection(client, owner_headers):
    job = client.post("/jobs", json={"company": "ViewCo", "role": "SWE"},
                      headers=owner_headers).json()
    assert client.get(f"/jobs/{job['id']}/resume",
                      headers=owner_headers).status_code == 404
    client.post(f"/jobs/{job['id']}/tailor", json={"jd_text": JD},
                headers=owner_headers)

    r = client.get(f"/jobs/{job['id']}/resume", headers=owner_headers)
    assert r.status_code == 200
    body = r.json()
    resume = body["resume"]

    assert resume["contact"]["name"] == "JORDAN SAMPLE"
    assert 25 <= len(resume["summary"].split()) <= 80
    assert len(resume["projects"]) == 3
    assert resume["experience"][0]["org"].startswith("CityWorks")

    plan = client.get(f"/jobs/{job['id']}/plan", headers=owner_headers).json()["plan"]
    n_selected = len(plan["experience"][0]["bullets"])
    assert len(resume["experience"][0]["bullets"]) == n_selected

    # descriptions are hyphen-free; skills keep their real names
    for role in resume["experience"]:
        for b in role["bullets"]:
            assert "-" not in b
    assert any("HTML/CSS" in g["items"] for g in resume["skills"]
               for _ in [0] if g["label"] == "Languages")


def test_resume_view_visible_to_viewer(client, viewer_headers, owner_headers):
    jobs = client.get("/jobs", headers=owner_headers).json()
    tailored = [j for j in jobs if j["status"] == "tailored"]
    assert tailored, "expected a tailored job from the previous test"
    r = client.get(f"/jobs/{tailored[0]['id']}/resume", headers=viewer_headers)
    assert r.status_code == 200

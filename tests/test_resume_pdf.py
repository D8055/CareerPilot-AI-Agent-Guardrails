"""Tailored-PDF endpoints: pure-Python generator, 1-page and 2-page variants."""


def _tailored_job(client, headers):
    job = client.post("/jobs", json={"company": "PdfCo", "role": "SWE"},
                      headers=headers).json()
    client.post(f"/jobs/{job['id']}/tailor",
                json={"jd_text": "React SQL Python data pipelines Docker Java"},
                headers=headers)
    return job


def test_status_reports_variants(client, owner_headers):
    job = _tailored_job(client, owner_headers)
    st = client.get(f"/jobs/{job['id']}/resume/status", headers=owner_headers).json()
    assert st["has_plan"] is True
    assert st["rendering_available"] is True
    assert set(st["variants"]) == {"onepage", "twopage"}
    assert st["variants"]["onepage"]["rendered"] is False


def test_render_both_variants_hit_page_targets(client, owner_headers):
    job = _tailored_job(client, owner_headers)

    one = client.post(f"/jobs/{job['id']}/resume/render?variant=onepage",
                      headers=owner_headers)
    assert one.status_code == 200
    assert one.json()["pages"] == 1 and one.json()["variant"] == "onepage"

    two = client.post(f"/jobs/{job['id']}/resume/render?variant=twopage",
                      headers=owner_headers)
    assert two.status_code == 200
    assert two.json()["pages"] <= 2 and two.json()["variant"] == "twopage"

    # both variants coexist and serve inline PDF
    for variant in ("onepage", "twopage"):
        pdf = client.get(f"/jobs/{job['id']}/resume.pdf?variant={variant}",
                         headers=owner_headers)
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content[:4] == b"%PDF"

    st = client.get(f"/jobs/{job['id']}/resume/status", headers=owner_headers).json()
    assert st["variants"]["onepage"]["rendered"]
    assert st["variants"]["twopage"]["rendered"]


def test_render_requires_plan(client, owner_headers):
    job = client.post("/jobs", json={"company": "NoPlan", "role": "X"},
                      headers=owner_headers).json()
    r = client.post(f"/jobs/{job['id']}/resume/render?variant=onepage",
                    headers=owner_headers)
    assert r.status_code == 400 and "tailor" in r.json()["detail"]


def test_render_is_owner_only(client, viewer_headers):
    r = client.post("/jobs/1/resume/render?variant=onepage", headers=viewer_headers)
    assert r.status_code == 403

"""Tailored-PDF endpoints. Rendering itself is Windows+Word only, so these
tests exercise the wiring with a monkeypatched renderer (no Word in CI)."""
import services


def _tailored_job(client, headers):
    job = client.post("/jobs", json={"company": "PdfCo", "role": "SWE"},
                      headers=headers).json()
    client.post(f"/jobs/{job['id']}/tailor",
                json={"jd_text": "React SQL Python data pipelines Docker"},
                headers=headers)
    return job


def test_status_reports_availability_and_no_pdf(client, owner_headers):
    job = _tailored_job(client, owner_headers)
    st = client.get(f"/jobs/{job['id']}/resume/status", headers=owner_headers).json()
    assert st["has_plan"] is True
    assert st["rendered"] is False
    assert "rendering_available" in st


def test_render_requires_master_resume(tmp_path, monkeypatch):
    # a truly fresh DB so "no master uploaded" holds regardless of test order
    import rendering
    from fastapi.testclient import TestClient

    from main import create_app
    monkeypatch.setattr(rendering, "render_available", lambda: True)
    app = create_app(f"sqlite:///{tmp_path / 'pdf.db'}")
    c = TestClient(app)
    tok = c.post("/auth/login", json={"email": "dhirenrao@gmail.com",
                                      "password": "test-password"}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    job = c.post("/jobs", json={"company": "PdfCo", "role": "SWE"}, headers=h).json()
    c.post(f"/jobs/{job['id']}/tailor", json={"jd_text": "React SQL Python"}, headers=h)
    r = c.post(f"/jobs/{job['id']}/resume/render", headers=h)
    assert r.status_code == 400 and "master resume" in r.json()["detail"]


def test_render_and_serve_pdf_roundtrip(client, owner_headers, viewer_headers,
                                        monkeypatch):
    import rendering
    fake_pdf = b"%PDF-1.7 fake tailored pdf bytes"
    monkeypatch.setattr(rendering, "render_available", lambda: True)
    monkeypatch.setattr(services, "render_resume_pdf", _fake_render(fake_pdf))

    # upload a master so the (real) path also has one
    client.post("/resume", headers=owner_headers,
                files={"file": ("master.docx", b"PK\x03\x04 master", "application/octet-stream")})
    job = _tailored_job(client, owner_headers)

    r = client.post(f"/jobs/{job['id']}/resume/render", headers=owner_headers)
    assert r.status_code == 200 and r.json()["rendered"] is True

    pdf = client.get(f"/jobs/{job['id']}/resume.pdf", headers=owner_headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content == fake_pdf
    assert "inline" in pdf.headers.get("content-disposition", "")

    # viewer can view but not render
    assert client.get(f"/jobs/{job['id']}/resume.pdf",
                      headers=viewer_headers).status_code == 200
    assert client.post(f"/jobs/{job['id']}/resume/render",
                       headers=viewer_headers).status_code == 403


def test_render_unavailable_is_clear(client, owner_headers, monkeypatch):
    import rendering
    monkeypatch.setattr(rendering, "render_available", lambda: False)
    job = _tailored_job(client, owner_headers)
    r = client.post(f"/jobs/{job['id']}/resume/render", headers=owner_headers)
    assert r.status_code == 400 and "Windows" in r.json()["detail"]


def _fake_render(pdf_bytes):
    from sqlalchemy import select

    from db import Artifact, Plan

    def render(db, job):
        plan = db.execute(select(Plan).filter_by(job_id=job.id)
                          .order_by(Plan.created_at.desc())).scalars().first()
        db.query(Artifact).filter_by(kind="resume_pdf", job_id=job.id).delete()
        db.add(Artifact(kind="resume_pdf", job_id=job.id,
                        plan_id=plan.id if plan else None,
                        filename="t.pdf", content_type="application/pdf",
                        data=pdf_bytes, meta={"failures": []}))
        db.commit()
        return {"rendered": True, "plan_id": plan.id if plan else None,
                "verified": True, "failures": [], "size": len(pdf_bytes)}
    return render

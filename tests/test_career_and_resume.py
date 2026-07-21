"""Owner career additions (plain text -> record + RAG) and resume upload."""


def test_owner_adds_career_item_and_rag_finds_it(client, owner_headers):
    r = client.post("/career/items", json={
        "text": "Built a Kafka consumer group in Spring Boot that upserts "
                "application events into MySQL idempotently.",
        "section": "CareerPilot analytics"}, headers=owner_headers)
    assert r.status_code == 201
    item = r.json()
    assert item["source"] == "owner" and item["tier"] == 1

    career = client.get("/career", headers=owner_headers).json()
    assert any(c["id"] == item["id"] for c in career)

    top = client.post("/rag/query", json={
        "text": "Kafka consumer Spring Boot MySQL", "k": 3},
        headers=owner_headers).json()
    assert item["id"] in [t["id"] for t in top]


def test_owner_items_survive_pool_reindex(client, owner_headers):
    import services
    from db import CareerItem
    factory = client.app.state.session_factory
    with factory() as db:
        before = db.query(CareerItem).filter_by(source="owner").count()
        assert before >= 1
        services.etl_pool(db)
        assert db.query(CareerItem).filter_by(source="owner").count() == before
        assert db.query(CareerItem).filter_by(source="pool").count() > 0


def test_career_item_validation_and_rbac(client, owner_headers, viewer_headers):
    assert client.post("/career/items", json={"text": "  "},
                       headers=owner_headers).status_code == 400
    assert client.post("/career/items", json={"text": "x"},
                       headers=viewer_headers).status_code == 403
    # pool items are not deletable; owner items are
    career = client.get("/career", headers=owner_headers).json()
    pool_item = next(c for c in career if c["source"] == "pool")
    own_item = next(c for c in career if c["source"] == "owner")
    assert client.delete(f"/career/items/{pool_item['id']}",
                         headers=owner_headers).status_code == 400
    assert client.delete(f"/career/items/{own_item['id']}",
                         headers=owner_headers).status_code == 200


def test_resume_upload_roundtrip(client, owner_headers, viewer_headers):
    assert client.get("/resume", headers=owner_headers).json()["uploaded"] is False
    data = b"PK\x03\x04 fake docx bytes for the roundtrip test"
    r = client.post("/resume", headers=owner_headers, files={
        "file": ("Dhiren_Rao_Resume.docx", data,
                 "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert r.status_code == 201

    meta = client.get("/resume", headers=owner_headers).json()
    assert meta["uploaded"] and meta["filename"] == "Dhiren_Rao_Resume.docx"
    assert meta["size"] == len(data)

    dl = client.get("/resume/download", headers=owner_headers)
    assert dl.status_code == 200 and dl.content == data

    # viewer can see metadata but cannot upload
    assert client.get("/resume", headers=viewer_headers).status_code == 200
    assert client.post("/resume", headers=viewer_headers,
                       files={"file": ("x.docx", b"y")}).status_code == 403


def test_resume_upload_rejects_empty(client, owner_headers):
    r = client.post("/resume", headers=owner_headers,
                    files={"file": ("empty.docx", b"")})
    assert r.status_code == 400

"""Smoke tests for the integration API endpoints."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
from main import app
import database
from utils import resolve_path

database.init_db()
client = TestClient(app)

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DOCX = os.path.join(BACKEND_DIR, "uploads",
    "5b03a5999bc2404ba1df910034a4f29d_咨询服务标准合同-调整板V4.docx")

_created_template_ids: list[int] = []
_created_document_ids: list[int] = []


def _cleanup_template(tid: int):
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT file_path FROM templates WHERE id = ?", (tid,)).fetchone()
        if row:
            file_path = resolve_path(row["file_path"])
            conn.execute("DELETE FROM review_tasks WHERE template_id = ?", (tid,))
            conn.execute("DELETE FROM documents WHERE template_id = ?", (tid,))
            conn.execute("DELETE FROM annotations WHERE template_id = ?", (tid,))
            conn.execute("DELETE FROM templates WHERE id = ?", (tid,))
            conn.commit()
            if os.path.exists(file_path):
                os.remove(file_path)
    finally:
        conn.close()


def _cleanup_document(did: int):
    conn = database.get_connection()
    try:
        row = conn.execute("SELECT file_path FROM documents WHERE id = ?", (did,)).fetchone()
        if row:
            file_path = resolve_path(row["file_path"])
            conn.execute("DELETE FROM review_tasks WHERE document_id = ?", (did,))
            conn.execute("DELETE FROM documents WHERE id = ?", (did,))
            conn.commit()
            if os.path.exists(file_path):
                os.remove(file_path)
    finally:
        conn.close()


def _get_first_template_id():
    resp = client.get("/api/integration/v1/templates")
    items = resp.json()
    return items[0]["id"] if items else None


def test_list_templates():
    resp = client.get("/api/integration/v1/templates")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_template_not_found():
    resp = client.get("/api/integration/v1/templates/99999")
    assert resp.status_code == 404


def test_upload_template():
    with open(TEST_DOCX, "rb") as f:
        resp = client.post(
            "/api/integration/v1/templates/upload",
            files={"file": ("test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] > 0
    assert data["paragraph_count"] > 0
    _cleanup_template(data["id"])


def test_get_template():
    tid = _get_first_template_id()
    if not tid:
        return
    resp = client.get(f"/api/integration/v1/templates/{tid}")
    assert resp.status_code == 200
    assert resp.json()["id"] == tid


def test_list_annotations():
    tid = _get_first_template_id()
    if not tid:
        return
    resp = client.get(f"/api/integration/v1/templates/{tid}/annotations")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_upload_document():
    tid = _get_first_template_id()
    if not tid:
        return
    with open(TEST_DOCX, "rb") as f:
        resp = client.post(
            f"/api/integration/v1/documents/upload?template_id={tid}",
            files={"file": ("test_doc.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] > 0
    _cleanup_document(data["id"])


def test_compare():
    tid = _get_first_template_id()
    if not tid:
        return
    from database import get_connection
    conn = get_connection()
    doc = conn.execute(
        "SELECT id FROM documents WHERE template_id = ? ORDER BY id DESC LIMIT 1",
        (tid,)
    ).fetchone()
    conn.close()
    if not doc:
        return
    resp = client.post(
        "/api/integration/v1/review/compare",
        json={"template_id": tid, "document_id": doc["id"]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "diffs" in data
    assert "violations" in data


def test_validate():
    tid = _get_first_template_id()
    if not tid:
        return
    from database import get_connection
    conn = get_connection()
    doc = conn.execute(
        "SELECT id FROM documents WHERE template_id = ? ORDER BY id DESC LIMIT 1",
        (tid,)
    ).fetchone()
    conn.close()
    if not doc:
        return
    resp = client.post(
        "/api/integration/v1/review/validate",
        json={"template_id": tid, "document_id": doc["id"]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data


def test_full_review():
    """End-to-end: upload docx + compare + validate in one call."""
    tid = _get_first_template_id()
    if not tid:
        return
    with open(TEST_DOCX, "rb") as f:
        resp = client.post(
            "/api/integration/v1/review/full",
            data={"template_id": str(tid)},
            files={"file": ("full_test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "document_id" in data
    assert data["document_id"] > 0
    assert "compare" in data
    assert "validate" in data
    assert "diffs" in data["compare"]
    assert "results" in data["validate"]
    _cleanup_document(data["document_id"])


def test_full_review_bad_template():
    """Non-existent template should return 404."""
    with open(TEST_DOCX, "rb") as f:
        resp = client.post(
            "/api/integration/v1/review/full",
            data={"template_id": "99999"},
            files={"file": ("test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    assert resp.status_code == 404


def test_full_review_bad_file():
    """Non-docx file should return 400."""
    tid = _get_first_template_id()
    if not tid:
        return
    resp = client.post(
        "/api/integration/v1/review/full",
        data={"template_id": str(tid)},
        files={"file": ("test.txt", b"hello world", "text/plain")}
    )
    assert resp.status_code == 400

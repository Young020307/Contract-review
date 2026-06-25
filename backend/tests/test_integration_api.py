"""Smoke tests for the integration API endpoints (external-only)."""
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
    items = resp.json()["data"]
    return items[0]["id"] if items else None


def _create_template():
    """Create a test template via the internal API, return its id."""
    with open(TEST_DOCX, "rb") as f:
        resp = client.post(
            "/api/templates/upload",
            files={"file": ("test_tpl.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    if resp.status_code != 200:
        return None
    return resp.json()["id"]


# ── External endpoint tests ──

def test_list_templates():
    resp = client.get("/api/integration/v1/templates")
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


def test_get_template_not_found():
    """Non-existent template under integration prefix should return 404 envelope."""
    resp = client.get("/api/integration/v1/templates/99999")
    assert resp.status_code == 404


# ── Review endpoint tests ──

def _do_review(review_type: int):
    """Helper: create a template via internal API, then review via integration API."""
    tid = _create_template()
    if tid is None:
        return None, None

    with open(TEST_DOCX, "rb") as f:
        resp = client.post(
            "/api/integration/v1/review",
            data={"template_id": str(tid), "review_type": str(review_type)},
            files={"file": ("review_test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    return resp, tid


def test_review_compare():
    """review_type=1: compare only."""
    resp, tid = _do_review(1)
    if resp is None:
        return
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "document_id" in data
    assert data["document_id"] > 0
    assert "compare" in data
    assert "diffs" in data["compare"]
    assert "violations" in data["compare"]
    assert "validate" not in data
    _cleanup_template(tid)
    _cleanup_document(data["document_id"])


def test_review_validate():
    """review_type=2: validate only."""
    resp, tid = _do_review(2)
    if resp is None:
        return
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "document_id" in data
    assert data["document_id"] > 0
    assert "validate" in data
    assert "results" in data["validate"]
    assert "compare" not in data
    _cleanup_template(tid)
    _cleanup_document(data["document_id"])


def test_review_full():
    """review_type=3: compare + validate."""
    resp, tid = _do_review(3)
    if resp is None:
        return
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "document_id" in data
    assert data["document_id"] > 0
    assert "compare" in data
    assert "validate" in data
    _cleanup_template(tid)
    _cleanup_document(data["document_id"])
    assert "diffs" in data["compare"]
    assert "results" in data["validate"]


def test_review_bad_template():
    """Non-existent template should return 404."""
    with open(TEST_DOCX, "rb") as f:
        resp = client.post(
            "/api/integration/v1/review",
            data={"template_id": "99999", "review_type": "1"},
            files={"file": ("test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    assert resp.status_code == 404


def test_review_bad_file():
    """Non-docx file should return 400."""
    tid = _get_first_template_id()
    if not tid:
        return
    resp = client.post(
        "/api/integration/v1/review",
        data={"template_id": str(tid), "review_type": "1"},
        files={"file": ("test.txt", b"hello world", "text/plain")}
    )
    assert resp.status_code == 400


def test_review_bad_type():
    """Invalid review_type should return 400."""
    tid = _get_first_template_id()
    if not tid:
        return
    with open(TEST_DOCX, "rb") as f:
        resp = client.post(
            "/api/integration/v1/review",
            data={"template_id": str(tid), "review_type": "99"},
            files={"file": ("test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        )
    assert resp.status_code == 400


# ── Envelope tests ──

def test_envelope_success_shape():
    """Successful responses must have {code, message, data, timestamp}."""
    resp = client.get("/api/integration/v1/templates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["message"] == "success"
    assert "data" in body
    assert isinstance(body["timestamp"], int) and body["timestamp"] > 0


def test_envelope_error_shape():
    """Error responses must have {code, message, data: null, timestamp}."""
    resp = client.get("/api/integration/v1/templates/99999")
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 404
    assert body["data"] is None
    assert isinstance(body["timestamp"], int) and body["timestamp"] > 0

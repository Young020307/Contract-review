# 格式合同智能审查 Demo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a demo web app for template upload, visual annotation, and two-mode review (tampering comparison + data validation) on docx contracts.

**Architecture:** Vue3 frontend talks to FastAPI backend over REST. Backend parses docx with python-docx, stores annotations/state in SQLite, computes character-level diffs and validation results. Frontend renders annotated templates with Mammoth + Fabric.js, and shows results with Monaco Editor diff views and custom validation tables.

**Tech Stack:** Vue3 + Vite + TypeScript + Element Plus + Mammoth + Fabric.js + Monaco Editor (frontend) | FastAPI + python-docx + difflib + Pydantic + SQLite (backend)

## Global Constraints

- All APIs return JSON; file uploads use multipart/form-data
- docx files stored on disk under `uploads/` directory, path tracked in DB
- Annotation is one-time per template; re-uploading same template overwrites
- Two review flows are independent and user-selectable after document upload
- Character-level diff (not paragraph/line level) for tampering comparison
- Data validation shows per-field pass/fail with rule description
- Single-user demo — no auth, no multi-tenancy
- Target: run backend with `uvicorn`, frontend with `npm run dev`

---

## File Structure

```
backend/
  main.py                # FastAPI app, CORS, route registrations, DB init
  database.py            # SQLite connection, table creation
  models.py              # Pydantic request/response models
  services/
    __init__.py
    parser.py            # DocxParser: extract paragraphs from docx bytes
    diff_engine.py       # DiffEngine: char-level diff between two texts
    validator.py         # RuleValidator: validate fillable fields against rules
  requirements.txt
  uploads/               # Uploaded .docx files stored here
  data.db                # SQLite database file (auto-created)

frontend/
  index.html
  package.json
  vite.config.ts
  tsconfig.json
  src/
    main.ts              # Vue app entry
    App.vue              # Root component with router-view
    router/
      index.ts           # Vue Router config (3 routes)
    api/
      index.ts           # All API functions (templates, annotations, documents, review)
    types/
      index.ts           # TypeScript interfaces
    views/
      TemplateList.vue   # Page 1: upload template, list templates
      AnnotationWorkbench.vue  # Page 2: Mammoth preview + Fabric.js toolbar
      ReviewWorkbench.vue      # Page 3: upload doc, choose flow, view results
    components/
      DocxPreview.vue          # Renders Mammoth-converted HTML in scrollable div
      AnnotationToolbar.vue    # Paragraph selector + zone type + rule config
      CompareDiffView.vue      # Monaco Editor diff editor with dual panel
      ValidationView.vue       # Dual-pane: rules table (L) + actual values (R)
```

---

## Backend Tasks

### Task 1: Backend project scaffold and database setup

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/database.py`
- Create: `backend/models.py`
- Create: `backend/main.py`
- Create: `backend/services/__init__.py`

**Interfaces:**
- Produces: `get_db()` — SQLite session dependency, `init_db()` — creates all tables
- Produces: Pydantic models in `models.py` — Template, Annotation, Document, ReviewTask, and all request/response schemas

- [ ] **Step 1: Write requirements.txt**

```
fastapi==0.115.6
uvicorn==0.34.0
python-multipart==0.0.19
python-docx==1.1.2
```

- [ ] **Step 2: Write database.py**

```python
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            paragraph_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL,
            paragraph_index INTEGER NOT NULL,
            zone_type TEXT NOT NULL CHECK(zone_type IN ('fixed','fillable')),
            rules TEXT DEFAULT '{}',
            FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER,
            name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            uploaded_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (template_id) REFERENCES templates(id)
        );
        CREATE TABLE IF NOT EXISTS review_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER,
            document_id INTEGER,
            task_type TEXT NOT NULL CHECK(task_type IN ('compare','validate','both')),
            result TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (template_id) REFERENCES templates(id),
            FOREIGN KEY (document_id) REFERENCES documents(id)
        );
    """)
    conn.commit()
    conn.close()
```

- [ ] **Step 3: Write models.py**

```python
from pydantic import BaseModel
from typing import Optional, Literal

# --- Annotation Rules ---
class ValidationRule(BaseModel):
    required: bool = True
    min_chars: int = 1
    max_chars: int = 200
    allowed_chars: str = "any"  # "chinese" | "number" | "alphanumeric" | "any" | "regex"
    regex: str = ""
    field_name: str = ""

# --- Request Models ---
class AnnotationItem(BaseModel):
    paragraph_index: int
    zone_type: Literal["fixed", "fillable"]
    rules: Optional[ValidationRule] = None

class AnnotationBatch(BaseModel):
    annotations: list[AnnotationItem]

class ReviewRequest(BaseModel):
    template_id: int
    document_id: int

# --- Response Models ---
class ParagraphInfo(BaseModel):
    index: int
    text: str

class TemplateResponse(BaseModel):
    id: int
    name: str
    paragraph_count: int
    created_at: str

class TemplateDetailResponse(BaseModel):
    id: int
    name: str
    paragraphs: list[ParagraphInfo]
    created_at: str

class DocumentResponse(BaseModel):
    id: int
    name: str
    template_id: Optional[int]
    paragraphs: list[ParagraphInfo]
    uploaded_at: str

class DiffSegment(BaseModel):
    type: Literal["equal", "insert", "delete", "replace"]
    template_range: tuple[int, int]
    doc_range: tuple[int, int]
    value: str

class Violation(BaseModel):
    paragraph: int
    type: str
    template_text: str
    actual_text: str

class CompareResult(BaseModel):
    template_text: str
    document_text: str
    diffs: list[DiffSegment]
    violations: list[Violation]

class FieldResult(BaseModel):
    paragraph: int
    field_name: str
    actual_value: str
    rule: str
    pass_: bool
    reason: str = ""

class ValidateResult(BaseModel):
    results: list[FieldResult]
```

- [ ] **Step 4: Write main.py (skeleton)**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db

app = FastAPI(title="格式合同智能审查系统 Demo")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/api/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Create services/__init__.py** (empty file: `touch backend/services/__init__.py`)

- [ ] **Step 6: Install dependencies and verify startup**

```bash
cd backend && pip install -r requirements.txt && uvicorn main:app --port 8000 &
sleep 3 && curl http://localhost:8000/api/health
```
Expected: `{"status":"ok"}`

- [ ] **Step 7: Commit**

```bash
git add backend/
git commit -m "feat: backend scaffold with database and models"
```

---

### Task 2: Docx parsing service

**Files:**
- Create: `backend/services/parser.py`

**Interfaces:**
- Produces: `DocxParser.parse(file_path: str) -> list[dict]` — returns `[{index: 0, text: "..."}, ...]`

- [ ] **Step 1: Write parser.py**

```python
from docx import Document

class DocxParser:
    @staticmethod
    def parse(file_path: str) -> list[dict]:
        doc = Document(file_path)
        paragraphs = []
        for i, para in enumerate(doc.paragraphs):
            text = para.text.strip()
            if text:  # skip empty paragraphs
                paragraphs.append({"index": i, "text": text})
        return paragraphs

    @staticmethod
    def extract_fixed_text(file_path: str, fixed_indices: set[int]) -> str:
        """Extract text only from paragraphs marked as fixed zone."""
        doc = Document(file_path)
        texts = []
        for i, para in enumerate(doc.paragraphs):
            if i in fixed_indices and para.text.strip():
                texts.append(para.text.strip())
        return "\n".join(texts)

    @staticmethod
    def extract_fillable_values(file_path: str, fillable_indices: set[int]) -> dict[int, str]:
        """Extract text from fillable paragraphs, keyed by paragraph index."""
        doc = Document(file_path)
        values = {}
        for i, para in enumerate(doc.paragraphs):
            if i in fillable_indices:
                values[i] = para.text.strip()
        return values
```

- [ ] **Step 2: Write and run unit test**

```bash
cd backend && python -c "
from services.parser import DocxParser
import sys
sys.path.insert(0, '.')
result = DocxParser.parse('../docs/咨询服务标准合同-调整板V4.docx')
print(f'Parsed {len(result)} paragraphs')
print(result[:3])
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/parser.py
git commit -m "feat: docx parsing service"
```

---

### Task 3: Template upload and management APIs

**Files:**
- Modify: `backend/main.py` (add routes)

**Interfaces:**
- Consumes: `DocxParser.parse()` from Task 2
- Produces: `POST /api/templates/upload`, `GET /api/templates`, `GET /api/templates/{id}`

- [ ] **Step 1: Add template routes to main.py**

```python
import os
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from database import get_connection
from models import TemplateResponse, TemplateDetailResponse, ParagraphInfo
from services.parser import DocxParser

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/templates/upload", response_model=TemplateResponse)
async def upload_template(file: UploadFile = File(...)):
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "只支持 .docx 文件")
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    paragraphs = DocxParser.parse(file_path)
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO templates (name, file_path, paragraph_count) VALUES (?, ?, ?)",
        (file.filename, file_path, len(paragraphs))
    )
    conn.commit()
    template_id = cur.lastrowid
    conn.close()
    return TemplateResponse(
        id=template_id,
        name=file.filename,
        paragraph_count=len(paragraphs),
        created_at=""
    )

@app.get("/api/templates", response_model=list[TemplateResponse])
def list_templates():
    conn = get_connection()
    rows = conn.execute("SELECT id, name, paragraph_count, created_at FROM templates ORDER BY id").fetchall()
    conn.close()
    return [TemplateResponse(id=r["id"], name=r["name"], paragraph_count=r["paragraph_count"], created_at=r["created_at"] or "") for r in rows]

@app.get("/api/templates/{template_id}", response_model=TemplateDetailResponse)
def get_template(template_id: int):
    conn = get_connection()
    row = conn.execute("SELECT id, name, file_path, created_at FROM templates WHERE id = ?", (template_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "模板不存在")
    paragraphs = DocxParser.parse(row["file_path"])
    conn.close()
    return TemplateDetailResponse(
        id=row["id"],
        name=row["name"],
        paragraphs=[ParagraphInfo(index=p["index"], text=p["text"]) for p in paragraphs],
        created_at=row["created_at"] or ""
    )
```

- [ ] **Step 2: Test upload**

```bash
cd backend && uvicorn main:app --port 8000 &
curl -X POST http://localhost:8000/api/templates/upload -F "file=@../docs/咨询服务标准合同-调整板V4.docx"
```
Expected: JSON with `id`, `name`, `paragraph_count`

- [ ] **Step 3: Test list and detail**

```bash
curl http://localhost:8000/api/templates
curl http://localhost:8000/api/templates/1
```

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat: template upload and management APIs"
```

---

### Task 4: Annotation CRUD APIs

**Files:**
- Modify: `backend/main.py` (add routes)

**Interfaces:**
- Consumes: `AnnotationBatch` from Task 1 models
- Produces: `POST /api/templates/{id}/annotations`, `GET /api/templates/{id}/annotations`

- [ ] **Step 1: Add annotation routes to main.py**

```python
from models import AnnotationBatch, AnnotationItem, ValidationRule

@app.post("/api/templates/{template_id}/annotations")
def save_annotations(template_id: int, body: AnnotationBatch):
    conn = get_connection()
    # Delete existing annotations for this template
    conn.execute("DELETE FROM annotations WHERE template_id = ?", (template_id,))
    for ann in body.annotations:
        rules_json = "{}"
        if ann.zone_type == "fillable" and ann.rules:
            rules_json = ann.rules.model_dump_json()
        conn.execute(
            "INSERT INTO annotations (template_id, paragraph_index, zone_type, rules) VALUES (?, ?, ?, ?)",
            (template_id, ann.paragraph_index, ann.zone_type, rules_json)
        )
    conn.commit()
    conn.close()
    return {"ok": True, "count": len(body.annotations)}

@app.get("/api/templates/{template_id}/annotations")
def get_annotations(template_id: int):
    conn = get_connection()
    rows = conn.execute(
        "SELECT paragraph_index, zone_type, rules FROM annotations WHERE template_id = ? ORDER BY paragraph_index",
        (template_id,)
    ).fetchall()
    conn.close()
    return [
        {
            "paragraph_index": r["paragraph_index"],
            "zone_type": r["zone_type"],
            "rules": r["rules"] if r["rules"] else "{}"
        }
        for r in rows
    ]
```

- [ ] **Step 2: Test annotation save/get**

```bash
curl -X POST http://localhost:8000/api/templates/1/annotations \
  -H "Content-Type: application/json" \
  -d '{"annotations":[{"paragraph_index":0,"zone_type":"fixed"},{"paragraph_index":3,"zone_type":"fillable","rules":{"required":true,"max_chars":50,"field_name":"公司名称"}}]}'

curl http://localhost:8000/api/templates/1/annotations
```

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: annotation CRUD APIs"
```

---

### Task 5: Document upload API

**Files:**
- Modify: `backend/main.py` (add routes)

**Interfaces:**
- Consumes: `DocxParser.parse()` from Task 2
- Produces: `POST /api/documents/upload`, `GET /api/documents/{id}`

- [ ] **Step 1: Add document routes to main.py**

```python
from models import DocumentResponse

@app.post("/api/documents/upload", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...), template_id: int = Query(...)):
    if not file.filename.endswith(".docx"):
        raise HTTPException(400, "只支持 .docx 文件")
    file_path = os.path.join(UPLOAD_DIR, f"doc_{template_id}_{file.filename}")
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    paragraphs = DocxParser.parse(file_path)
    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO documents (template_id, name, file_path) VALUES (?, ?, ?)",
        (template_id, file.filename, file_path)
    )
    conn.commit()
    doc_id = cur.lastrowid
    conn.close()
    return DocumentResponse(
        id=doc_id,
        name=file.filename,
        template_id=template_id,
        paragraphs=[ParagraphInfo(index=p["index"], text=p["text"]) for p in paragraphs],
        uploaded_at=""
    )

@app.get("/api/documents/{document_id}", response_model=DocumentResponse)
def get_document(document_id: int):
    conn = get_connection()
    row = conn.execute("SELECT id, name, template_id, file_path, uploaded_at FROM documents WHERE id = ?", (document_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "文件不存在")
    paragraphs = DocxParser.parse(row["file_path"])
    conn.close()
    return DocumentResponse(
        id=row["id"],
        name=row["name"],
        template_id=row["template_id"],
        paragraphs=[ParagraphInfo(index=p["index"], text=p["text"]) for p in paragraphs],
        uploaded_at=row["uploaded_at"] or ""
    )
```

- [ ] **Step 2: Test with dummy docx**

```bash
# Create a test docx or use the existing one
curl -X POST "http://localhost:8000/api/documents/upload?template_id=1" -F "file=@../docs/咨询服务标准合同-调整板V4-测试.docx"
curl http://localhost:8000/api/documents/1
```

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: document upload API"
```

---

### Task 6: Diff engine service

**Files:**
- Create: `backend/services/diff_engine.py`

**Interfaces:**
- Produces: `DiffEngine.compare(template_text: str, doc_text: str) -> dict` — returns `{diffs: [...], violations: [...]}`

- [ ] **Step 1: Write diff_engine.py**

```python
import difflib

class DiffEngine:
    @staticmethod
    def compare(template_text: str, doc_text: str) -> dict:
        """Compare two texts, return char-level diff segments and violation list."""
        sm = difflib.SequenceMatcher(None, template_text, doc_text)
        diffs = []
        violations = []

        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            diff = {
                "type": tag,  # "equal", "insert", "delete", "replace"
                "template_range": [i1, i2],
                "doc_range": [j1, j2],
                "value": ""
            }
            if tag == "equal":
                diff["value"] = template_text[i1:i2]
            elif tag == "delete":
                diff["value"] = template_text[i1:i2]
            elif tag == "insert":
                diff["value"] = doc_text[j1:j2]
            elif tag == "replace":
                diff["value"] = doc_text[j1:j2]
            diffs.append(diff)

            if tag in ("delete", "insert", "replace"):
                violations.append({
                    "paragraph": 0,
                    "type": "tamper",
                    "template_text": template_text[i1:i2] if tag != "insert" else "(新增)",
                    "actual_text": doc_text[j1:j2] if tag != "delete" else "(删除)"
                })

        return {"diffs": diffs, "violations": violations}
```

- [ ] **Step 2: Test inline**

```bash
cd backend && python -c "
from services.diff_engine import DiffEngine
result = DiffEngine.compare('本合同双方经友好协商条款第一项', '本合同双方经友好协上条款第一项')
print(result['diffs'])
print(result['violations'])
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/diff_engine.py
git commit -m "feat: diff engine service"
```

---

### Task 7: Compare review API

**Files:**
- Modify: `backend/main.py` (add route)

**Interfaces:**
- Consumes: `DocxParser.extract_fixed_text()` from Task 2, `DiffEngine.compare()` from Task 6
- Produces: `POST /api/review/compare`

- [ ] **Step 1: Add compare route to main.py**

```python
from services.diff_engine import DiffEngine

@app.post("/api/review/compare")
def review_compare(body: ReviewRequest):
    conn = get_connection()
    template = conn.execute("SELECT id, file_path FROM templates WHERE id = ?", (body.template_id,)).fetchone()
    document = conn.execute("SELECT id, file_path FROM documents WHERE id = ?", (body.document_id,)).fetchone()
    if not template or not document:
        conn.close()
        raise HTTPException(404, "模板或文件不存在")

    # Get fixed paragraph indices from annotations
    annotations = conn.execute(
        "SELECT paragraph_index FROM annotations WHERE template_id = ? AND zone_type = 'fixed'",
        (body.template_id,)
    ).fetchall()
    fixed_indices = {a["paragraph_index"] for a in annotations}

    template_text = DocxParser.extract_fixed_text(template["file_path"], fixed_indices)
    doc_text = DocxParser.extract_fixed_text(document["file_path"], fixed_indices)

    result = DiffEngine.compare(template_text, doc_text)
    result["template_text"] = template_text
    result["document_text"] = doc_text

    # Save review task
    import json
    conn.execute(
        "INSERT INTO review_tasks (template_id, document_id, task_type, result) VALUES (?, ?, 'compare', ?)",
        (body.template_id, body.document_id, json.dumps(result, ensure_ascii=False))
    )
    conn.commit()
    conn.close()
    return result
```

- [ ] **Step 2: Test with annotated template and document**

```bash
curl -X POST http://localhost:8000/api/review/compare \
  -H "Content-Type: application/json" \
  -d '{"template_id":1,"document_id":1}'
```

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: compare review API"
```

---

### Task 8: Validation engine service

**Files:**
- Create: `backend/services/validator.py`

**Interfaces:**
- Produces: `RuleValidator.validate(values: dict, annotations: dict) -> dict` — returns `{results: [...]}`

- [ ] **Step 1: Write validator.py**

```python
import re
import json

class RuleValidator:
    CHAR_PATTERNS = {
        "chinese": re.compile(r'^[一-鿿]+$'),
        "number": re.compile(r'^\d+$'),
        "alphanumeric": re.compile(r'^[a-zA-Z0-9一-鿿]+$'),
    }

    @staticmethod
    def validate(values: dict, annotations: list[dict]) -> dict:
        """Validate extracted fillable values against annotation rules.
        values: {paragraph_index: "actual text"}
        annotations: [{paragraph_index, zone_type, rules}, ...]
        """
        results = []
        for ann in annotations:
            pi = ann["paragraph_index"]
            rules = json.loads(ann["rules"]) if isinstance(ann["rules"], str) else ann["rules"]
            if not rules:
                continue

            actual_value = values.get(pi, "")
            field_result = {
                "paragraph": pi,
                "field_name": rules.get("field_name", f"段落{pi}"),
                "actual_value": actual_value,
                "rule": RuleValidator._describe_rule(rules),
                "pass": True,
                "reason": ""
            }

            # Required check
            if rules.get("required", False) and not actual_value:
                field_result["pass"] = False
                field_result["reason"] = "必填字段为空"
                results.append(field_result)
                continue

            if not actual_value:
                results.append(field_result)
                continue

            # Min chars
            min_chars = rules.get("min_chars", 0)
            if len(actual_value) < min_chars:
                field_result["pass"] = False
                field_result["reason"] = f"字数不足：最少{min_chars}字，实际{len(actual_value)}字"

            # Max chars
            max_chars = rules.get("max_chars", 9999)
            if len(actual_value) > max_chars:
                field_result["pass"] = False
                field_result["reason"] = f"字数超限：最多{max_chars}字，实际{len(actual_value)}字"

            # Allowed chars
            allowed = rules.get("allowed_chars", "any")
            if allowed in RuleValidator.CHAR_PATTERNS:
                pattern = RuleValidator.CHAR_PATTERNS[allowed]
                if not pattern.match(actual_value):
                    field_result["pass"] = False
                    field_result["reason"] = f"字符类型不符：要求{allowed}"

            # Custom regex
            if allowed == "regex" and rules.get("regex"):
                if not re.match(rules["regex"], actual_value):
                    field_result["pass"] = False
                    field_result["reason"] = f"格式不符：需匹配 {rules['regex']}"

            results.append(field_result)

        return {"results": results}

    @staticmethod
    def _describe_rule(rules: dict) -> str:
        parts = []
        if rules.get("required"):
            parts.append("必填")
        min_c = rules.get("min_chars", 0)
        max_c = rules.get("max_chars", 9999)
        if min_c and max_c < 9999:
            parts.append(f"{min_c}-{max_c}字")
        elif min_c:
            parts.append(f"最少{min_c}字")
        elif max_c < 9999:
            parts.append(f"最多{max_c}字")
        allowed = rules.get("allowed_chars", "any")
        if allowed != "any":
            parts.append(allowed)
        return "+".join(parts) if parts else "无规则"
```

- [ ] **Step 2: Test inline**

```bash
cd backend && python -c "
from services.validator import RuleValidator
annotations = [{
    'paragraph_index': 3,
    'rules': {'required': True, 'min_chars': 2, 'max_chars': 50, 'allowed_chars': 'chinese', 'field_name': '公司名称'}
}]
result = RuleValidator.validate({3: '测试有限公司'}, annotations)
print(result)
result2 = RuleValidator.validate({3: ''}, annotations)
print(result2)
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/validator.py
git commit -m "feat: validation engine service"
```

---

### Task 9: Validation review API

**Files:**
- Modify: `backend/main.py` (add route)

**Interfaces:**
- Consumes: `DocxParser.extract_fillable_values()` from Task 2, `RuleValidator.validate()` from Task 8
- Produces: `POST /api/review/validate`

- [ ] **Step 1: Add validate route to main.py**

```python
from services.validator import RuleValidator

@app.post("/api/review/validate")
def review_validate(body: ReviewRequest):
    conn = get_connection()
    template = conn.execute("SELECT id, file_path FROM templates WHERE id = ?", (body.template_id,)).fetchone()
    document = conn.execute("SELECT id, file_path FROM documents WHERE id = ?", (body.document_id,)).fetchone()
    if not template or not document:
        conn.close()
        raise HTTPException(404, "模板或文件不存在")

    annotations = conn.execute(
        "SELECT paragraph_index, zone_type, rules FROM annotations WHERE template_id = ? AND zone_type = 'fillable'",
        (body.template_id,)
    ).fetchall()
    fillable_indices = {a["paragraph_index"] for a in annotations}

    values = DocxParser.extract_fillable_values(document["file_path"], fillable_indices)

    ann_list = [{"paragraph_index": a["paragraph_index"], "rules": a["rules"]} for a in annotations]
    result = RuleValidator.validate(values, ann_list)

    import json
    conn.execute(
        "INSERT INTO review_tasks (template_id, document_id, task_type, result) VALUES (?, ?, 'validate', ?)",
        (body.template_id, body.document_id, json.dumps(result, ensure_ascii=False))
    )
    conn.commit()
    conn.close()
    return result
```

- [ ] **Step 2: Test**

```bash
curl -X POST http://localhost:8000/api/review/validate \
  -H "Content-Type: application/json" \
  -d '{"template_id":1,"document_id":1}'
```

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: validation review API"
```

---

## Frontend Tasks

### Task 10: Frontend scaffold

**Files:**
- Create: `frontend/package.json`, `frontend/index.html`, `frontend/vite.config.ts`, `frontend/tsconfig.json`
- Create: `frontend/src/main.ts`, `frontend/src/App.vue`, `frontend/src/router/index.ts`
- Create: `frontend/src/types/index.ts`, `frontend/src/api/index.ts`

**Interfaces:**
- Produces: Vue3 app with 3 routes and typed API client layer

- [ ] **Step 1: Write package.json**

```json
{
  "name": "contract-review-demo",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "vue-tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3.5.13",
    "vue-router": "^4.5.0",
    "element-plus": "^2.9.2",
    "mammoth": "^1.8.0",
    "fabric": "^6.5.1",
    "monaco-editor": "^0.52.2",
    "axios": "^1.7.9"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.2.1",
    "typescript": "^5.7.3",
    "vite": "^6.0.7",
    "vue-tsc": "^2.2.0"
  }
}
```

- [ ] **Step 2: Write vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
```

- [ ] **Step 3: Write index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>格式合同智能审查系统 Demo</title>
</head>
<body>
  <div id="app"></div>
  <script type="module" src="/src/main.ts"></script>
</body>
</html>
```

- [ ] **Step 4: Write types/index.ts**

```typescript
export interface ParagraphInfo {
  index: number
  text: string
}

export interface TemplateInfo {
  id: number
  name: string
  paragraph_count: number
  created_at: string
}

export interface TemplateDetail {
  id: number
  name: string
  paragraphs: ParagraphInfo[]
  created_at: string
}

export interface ValidationRule {
  required: boolean
  min_chars: number
  max_chars: number
  allowed_chars: 'chinese' | 'number' | 'alphanumeric' | 'any' | 'regex'
  regex: string
  field_name: string
}

export interface AnnotationItem {
  paragraph_index: number
  zone_type: 'fixed' | 'fillable'
  rules?: ValidationRule
}

export interface AnnotationEntry {
  paragraph_index: number
  zone_type: string
  rules: string
}

export interface DocumentInfo {
  id: number
  template_id: number | null
  name: string
  paragraphs: ParagraphInfo[]
  uploaded_at: string
}

export interface DiffSegment {
  type: 'equal' | 'insert' | 'delete' | 'replace'
  template_range: [number, number]
  doc_range: [number, number]
  value: string
}

export interface CompareViolation {
  paragraph: number
  type: string
  template_text: string
  actual_text: string
}

export interface CompareResult {
  template_text: string
  document_text: string
  diffs: DiffSegment[]
  violations: CompareViolation[]
}

export interface FieldResult {
  paragraph: number
  field_name: string
  actual_value: string
  rule: string
  pass: boolean
  reason: string
}

export interface ValidateResult {
  results: FieldResult[]
}
```

- [ ] **Step 5: Write api/index.ts**

```typescript
import axios from 'axios'
import type {
  TemplateInfo, TemplateDetail, AnnotationItem, AnnotationEntry,
  DocumentInfo, CompareResult, ValidateResult
} from '../types'

const api = axios.create({ baseURL: '/api' })

export async function uploadTemplate(file: File): Promise<TemplateInfo> {
  const fd = new FormData(); fd.append('file', file)
  const { data } = await api.post('/templates/upload', fd)
  return data
}

export async function listTemplates(): Promise<TemplateInfo[]> {
  const { data } = await api.get('/templates')
  return data
}

export async function getTemplate(id: number): Promise<TemplateDetail> {
  const { data } = await api.get(`/templates/${id}`)
  return data
}

export async function saveAnnotations(templateId: number, annotations: AnnotationItem[]): Promise<void> {
  await api.post(`/templates/${templateId}/annotations`, { annotations })
}

export async function getAnnotations(templateId: number): Promise<AnnotationEntry[]> {
  const { data } = await api.get(`/templates/${templateId}/annotations`)
  return data
}

export async function uploadDocument(file: File, templateId: number): Promise<DocumentInfo> {
  const fd = new FormData(); fd.append('file', file)
  const { data } = await api.post(`/documents/upload?template_id=${templateId}`, fd)
  return data
}

export async function getDocument(id: number): Promise<DocumentInfo> {
  const { data } = await api.get(`/documents/${id}`)
  return data
}

export async function reviewCompare(templateId: number, documentId: number): Promise<CompareResult> {
  const { data } = await api.post('/review/compare', { template_id: templateId, document_id: documentId })
  return data
}

export async function reviewValidate(templateId: number, documentId: number): Promise<ValidateResult> {
  const { data } = await api.post('/review/validate', { template_id: templateId, document_id: documentId })
  return data
}
```

- [ ] **Step 6: Write router/index.ts**

```typescript
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'templates', component: () => import('../views/TemplateList.vue') },
    { path: '/annotate/:id', name: 'annotate', component: () => import('../views/AnnotationWorkbench.vue'), props: true },
    { path: '/review', name: 'review', component: () => import('../views/ReviewWorkbench.vue') },
  ]
})

export default router
```

- [ ] **Step 7: Write main.ts and App.vue**

```typescript
// main.ts
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(ElementPlus)
app.use(router)
app.mount('#app')
```

```vue
<!-- App.vue -->
<template>
  <div class="app-container">
    <header class="app-header">
      <h1 @click="$router.push('/')">格式合同智能审查系统 Demo</h1>
      <nav>
        <router-link to="/">模板管理</router-link>
        <router-link to="/review">审查工作台</router-link>
      </nav>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
.app-container { min-height: 100vh; background: #f0f2f5; }
.app-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 24px; background: #fff; border-bottom: 1px solid #e4e7ed;
}
.app-header h1 { font-size: 18px; cursor: pointer; }
.app-header nav a { margin-left: 16px; text-decoration: none; color: #409eff; }
.app-main { padding: 24px; max-width: 1400px; margin: 0 auto; }
</style>
```

- [ ] **Step 8: Install dependencies and verify startup**

```bash
cd frontend && npm install && npm run dev
```
Open http://localhost:5173 — should show empty app with header and nav.

- [ ] **Step 9: Commit**

```bash
git add frontend/
git commit -m "feat: frontend scaffold with router and API layer"
```

---

### Task 11: Template management page

**Files:**
- Create: `frontend/src/views/TemplateList.vue`

**Interfaces:**
- Consumes: `uploadTemplate()`, `listTemplates()` from Task 10 API layer

- [ ] **Step 1: Write TemplateList.vue**

```vue
<template>
  <div class="template-page">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>模板管理</span>
          <el-upload :show-file-list="false" :before-upload="handleUpload" accept=".docx">
            <el-button type="primary">上传模板</el-button>
          </el-upload>
        </div>
      </template>
      <el-table :data="templates" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="模板名称" />
        <el-table-column prop="paragraph_count" label="段落数" width="100" />
        <el-table-column prop="created_at" label="上传时间" width="180" />
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.annotated ? 'success' : 'warning'">
              {{ row.annotated ? '已标注' : '未标注' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button type="primary" size="small" @click="$router.push(`/annotate/${row.id}`)">
              标注
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listTemplates, uploadTemplate, getAnnotations } from '../api'
import type { TemplateInfo } from '../types'

interface TemplateRow extends TemplateInfo { annotated: boolean }
const templates = ref<TemplateRow[]>([])

onMounted(async () => {
  await loadTemplates()
})

async function loadTemplates() {
  const list = await listTemplates()
  const enriched: TemplateRow[] = []
  for (const t of list) {
    try {
      const anns = await getAnnotations(t.id)
      enriched.push({ ...t, annotated: anns.length > 0 })
    } catch {
      enriched.push({ ...t, annotated: false })
    }
  }
  templates.value = enriched
}

async function handleUpload(file: File) {
  await uploadTemplate(file)
  ElMessage.success('模板上传成功')
  await loadTemplates()
  return false
}
</script>

<style scoped>
.card-header { display: flex; align-items: center; justify-content: space-between; }
</style>
```

- [ ] **Step 2: Run dev server and verify page renders**

```bash
cd frontend && npm run dev
```
Open http://localhost:5173 — should see template list page with upload button.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/TemplateList.vue
git commit -m "feat: template management page"
```

---

### Task 12: Annotation workbench page

**Files:**
- Create: `frontend/src/views/AnnotationWorkbench.vue`
- Create: `frontend/src/components/DocxPreview.vue`
- Create: `frontend/src/components/AnnotationToolbar.vue`

**Interfaces:**
- Consumes: `getTemplate()`, `getAnnotations()`, `saveAnnotations()` from Task 10
- Produces: Functional annotation page with Mammoth preview + annotation toolbar

- [ ] **Step 1: Write DocxPreview.vue**

```vue
<template>
  <div class="preview-container" ref="container">
    <div v-if="loading" class="loading">解析文档中...</div>
    <div v-html="htmlContent" class="preview-content"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import mammoth from 'mammoth'

const props = defineProps<{ fileUrl: string }>()
const htmlContent = ref('')
const loading = ref(false)

watch(() => props.fileUrl, async (url) => {
  if (!url) return
  loading.value = true
  const res = await fetch(url)
  const blob = await res.arrayBuffer()
  const result = await mammoth.convertToHtml({ arrayBuffer: blob })
  htmlContent.value = result.value
  loading.value = false
}, { immediate: true })
</script>

<style scoped>
.preview-container { height: 100%; overflow-y: auto; padding: 24px; background: #fff; border: 1px solid #e4e7ed; }
.preview-content { max-width: 800px; margin: 0 auto; }
.loading { text-align: center; padding: 40px; color: #909399; }
</style>
```

- [ ] **Step 2: Write AnnotationToolbar.vue**

```vue
<template>
  <div class="toolbar">
    <h3>标注工具</h3>
    <p class="hint">点击段落选中，然后选择区域类型</p>

    <div class="zone-actions">
      <el-button :type="selectedZone === 'fixed' ? 'danger' : 'default'" @click="markAs('fixed')">
        标记为固定区
      </el-button>
      <el-button :type="selectedZone === 'fillable' ? 'success' : 'default'" @click="markAs('fillable')">
        标记为填充区
      </el-button>
    </div>

    <div v-if="currentParagraph !== null" class="para-info">
      <p><strong>当前段落:</strong> {{ currentParagraph }}</p>
      <p class="text-preview">{{ paraText }}</p>
    </div>

    <!-- Fillable rules config -->
    <div v-if="selectedZone === 'fillable' && currentParagraph !== null" class="rules-config">
      <h4>校验规则</h4>
      <el-form label-width="80px" size="small">
        <el-form-item label="字段名称">
          <el-input v-model="rules.field_name" placeholder="如：公司名称" />
        </el-form-item>
        <el-form-item label="必填">
          <el-switch v-model="rules.required" />
        </el-form-item>
        <el-form-item label="最少字数">
          <el-input-number v-model="rules.min_chars" :min="0" :max="500" />
        </el-form-item>
        <el-form-item label="最多字数">
          <el-input-number v-model="rules.max_chars" :min="1" :max="1000" />
        </el-form-item>
        <el-form-item label="字符类型">
          <el-select v-model="rules.allowed_chars">
            <el-option label="不限制" value="any" />
            <el-option label="仅中文" value="chinese" />
            <el-option label="仅数字" value="number" />
            <el-option label="字母+数字+中文" value="alphanumeric" />
            <el-option label="正则表达式" value="regex" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="rules.allowed_chars === 'regex'" label="正则">
          <el-input v-model="rules.regex" placeholder="如: ^1[3-9]\d{9}$" />
        </el-form-item>
        <el-button type="primary" @click="applyRule">确认规则</el-button>
      </el-form>
    </div>

    <el-divider />
    <h4>标注列表</h4>
    <div v-if="annotations.length === 0" class="empty">暂无标注</div>
    <div v-for="a in annotations" :key="a.paragraph_index" class="ann-item" @click="$emit('selectPara', a.paragraph_index)">
      <el-tag :type="a.zone_type === 'fixed' ? 'danger' : 'success'" size="small">
        {{ a.zone_type === 'fixed' ? '固定' : '填充' }}
      </el-tag>
      <span>段落 {{ a.paragraph_index }}</span>
      <span v-if="a.rules?.field_name">- {{ a.rules.field_name }}</span>
    </div>

    <el-divider />
    <el-button type="primary" @click="save" :loading="saving">保存标注</el-button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { AnnotationItem, ValidationRule } from '../types'

const props = defineProps<{
  currentParagraph: number | null
  paraText: string
  annotations: AnnotationItem[]
  saving: boolean
}>()

const emit = defineEmits<{
  markAs: [zone: 'fixed' | 'fillable']
  applyRule: [rule: ValidationRule, paraIndex: number]
  save: []
  selectPara: [index: number]
}>()

const selectedZone = ref<'fixed' | 'fillable' | null>(null)

const rules = ref<ValidationRule>({
  required: true, min_chars: 1, max_chars: 200,
  allowed_chars: 'any', regex: '', field_name: ''
})

function markAs(zone: 'fixed' | 'fillable') {
  selectedZone.value = zone
  emit('markAs', zone)
}

function applyRule() {
  if (props.currentParagraph === null) return
  emit('applyRule', { ...rules.value }, props.currentParagraph)
}
</script>
```

- [ ] **Step 3: Write AnnotationWorkbench.vue**

```vue
<template>
  <div class="workbench">
    <div class="workbench-left">
      <DocxPreview :file-url="docxUrl" />
    </div>
    <div class="workbench-right">
      <AnnotationToolbar
        :current-paragraph="currentParagraph"
        :para-text="paraText"
        :annotations="annotations"
        :saving="saving"
        @mark-as="markAs"
        @apply-rule="handleApplyRule"
        @save="handleSave"
        @select-para="handleSelectPara"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getTemplate, saveAnnotations, getAnnotations } from '../api'
import type { AnnotationItem, ValidationRule, TemplateDetail } from '../types'
import DocxPreview from '../components/DocxPreview.vue'
import AnnotationToolbar from '../components/AnnotationToolbar.vue'

const route = useRoute()
const router = useRouter()
const templateId = Number(route.params.id)
const docxUrl = ref('')
const currentParagraph = ref<number | null>(null)
const paraText = ref('')
const annotations = ref<AnnotationItem[]>([])
const saving = ref(false)

onMounted(async () => {
  const t: TemplateDetail = await getTemplate(templateId)
  docxUrl.value = `/api/documents/proxy-template/${templateId}`
  // Load existing annotations
  try {
    const existing = await getAnnotations(templateId)
    annotations.value = existing.map(a => ({
      paragraph_index: a.paragraph_index,
      zone_type: a.zone_type as 'fixed' | 'fillable',
      rules: a.rules ? JSON.parse(a.rules) : undefined
    }))
  } catch { /* no existing annotations */ }
})

function handleSelectPara(index: number) {
  currentParagraph.value = index
}

function markAs(zone: 'fixed' | 'fillable') {
  if (currentParagraph.value === null) return
  const existing = annotations.value.findIndex(a => a.paragraph_index === currentParagraph.value)
  const item: AnnotationItem = { paragraph_index: currentParagraph.value!, zone_type: zone }
  if (existing >= 0) {
    annotations.value[existing] = item
  } else {
    annotations.value.push(item)
  }
}

function handleApplyRule(rule: ValidationRule, paraIndex: number) {
  const existing = annotations.value.findIndex(a => a.paragraph_index === paraIndex)
  if (existing >= 0) {
    annotations.value[existing].rules = rule
  } else {
    annotations.value.push({ paragraph_index: paraIndex, zone_type: 'fillable', rules: rule })
  }
}

async function handleSave() {
  saving.value = true
  await saveAnnotations(templateId, annotations.value)
  saving.value = false
  ElMessage.success('标注已保存')
}
</script>

<style scoped>
.workbench { display: flex; gap: 16px; height: calc(100vh - 100px); }
.workbench-left { flex: 1; overflow-y: auto; }
.workbench-right { width: 360px; flex-shrink: 0; }
</style>
```

- [ ] **Step 4: Add proxy route for template file**

In `backend/main.py`:
```python
@app.get("/api/documents/proxy-template/{template_id}")
async def proxy_template_file(template_id: int):
    conn = get_connection()
    row = conn.execute("SELECT file_path FROM templates WHERE id = ?", (template_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404)
    # Add to top of main.py: from fastapi.responses import FileResponse
from fastapi.responses import FileResponse
    return FileResponse(row["file_path"], media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
```

- [ ] **Step 5: Test annotation workflow**

Start both backend and frontend, upload template, open annotation page.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/AnnotationWorkbench.vue frontend/src/components/DocxPreview.vue frontend/src/components/AnnotationToolbar.vue backend/main.py
git commit -m "feat: annotation workbench page"
```

---

### Task 13: Compare diff view component

**Files:**
- Create: `frontend/src/components/CompareDiffView.vue`

**Interfaces:**
- Consumes: `CompareResult` type from Task 10
- Produces: Functional Monaco diff editor component

- [ ] **Step 1: Install monaco-editor vite plugin**

```bash
cd frontend && npm install vite-plugin-monaco-editor
```

Update `vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import monacoEditorPlugin from 'vite-plugin-monaco-editor'

export default defineConfig({
  plugins: [
    vue(),
    monacoEditorPlugin({ languageWorkers: ['editorWorkerService'] })
  ],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' }
  }
})
```

- [ ] **Step 2: Write CompareDiffView.vue**

```vue
<template>
  <div class="diff-container">
    <div class="diff-header">
      <h3>防篡改比对结果</h3>
      <span class="violation-count" v-if="violations.length > 0">
        发现 {{ violations.length }} 处差异
      </span>
      <el-tag v-else type="success">未发现篡改</el-tag>
    </div>
    <div ref="editorContainer" class="diff-editor"></div>
    <div v-if="violations.length > 0" class="violation-list">
      <h4>差异详情</h4>
      <div v-for="(v, i) in violations" :key="i" class="violation-item" @click="goToViolation(i)">
        <el-tag type="danger">篡改</el-tag>
        <span class="v-template">模板: {{ truncate(v.template_text) }}</span>
        <span class="v-actual">实际: {{ truncate(v.actual_text) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import * as monaco from 'monaco-editor'
import type { CompareResult } from '../types'

const props = defineProps<{ result: CompareResult }>()
const editorContainer = ref<HTMLDivElement | null>(null)
let diffEditor: monaco.editor.IStandaloneDiffEditor | null = null

const violations = ref(props.result?.violations ?? [])

onMounted(() => {
  if (!editorContainer.value) return
  diffEditor = monaco.editor.createDiffEditor(editorContainer.value, {
    readOnly: true,
    automaticLayout: true,
    renderSideBySide: true,
    scrollBeyondLastLine: false,
    minimap: { enabled: false }
  })
  updateModel()
})

watch(() => props.result, () => {
  violations.value = props.result?.violations ?? []
  updateModel()
})

function updateModel() {
  if (!diffEditor) return
  const original = monaco.editor.createModel(props.result.template_text, 'text/plain')
  const modified = monaco.editor.createModel(props.result.document_text, 'text/plain')
  diffEditor.setModel({ original, modified })
}

function truncate(text: string): string {
  return text.length > 30 ? text.slice(0, 30) + '...' : text
}

function goToViolation(index: number) {
  if (!diffEditor) return
  const v = violations.value[index]
  const diff = props.result.diffs[index]
  if (diff) {
    diffEditor.setSelection({
      startLineNumber: 1,
      startColumn: diff.doc_range[0] + 1,
      endLineNumber: 1,
      endColumn: diff.doc_range[1] + 1
    })
  }
}
</script>

<style scoped>
.diff-container { height: 100%; display: flex; flex-direction: column; }
.diff-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.diff-editor { flex: 1; min-height: 400px; border: 1px solid #e4e7ed; }
.violation-count { color: #f56c6c; font-weight: bold; }
.violation-list { margin-top: 16px; }
.violation-item { padding: 8px; border: 1px solid #fde2e2; border-radius: 4px; margin-bottom: 4px; cursor: pointer; display: flex; gap: 12px; align-items: center; }
.violation-item:hover { background: #fef0f0; }
</style>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CompareDiffView.vue frontend/vite.config.ts
git commit -m "feat: Monaco Editor diff view component"
```

---

### Task 14: Validation view component

**Files:**
- Create: `frontend/src/components/ValidationView.vue`

**Interfaces:**
- Consumes: `ValidateResult` type from Task 10
- Produces: Dual-pane validation result display

- [ ] **Step 1: Write ValidationView.vue**

```vue
<template>
  <div class="validation-container">
    <div class="val-header">
      <h3>数据校验结果</h3>
      <span>
        通过 {{ passCount }} / 共 {{ result.results.length }} 项
      </span>
    </div>
    <div class="dual-pane">
      <div class="pane left-pane">
        <h4>模板规则</h4>
        <div v-for="r in result.results" :key="r.paragraph" class="rule-row">
          <div class="field-label">{{ r.field_name }} <el-tag size="small">段落{{ r.paragraph }}</el-tag></div>
          <div class="field-rule">{{ r.rule }}</div>
        </div>
      </div>
      <div class="pane right-pane">
        <h4>实际填写</h4>
        <div v-for="r in result.results" :key="r.paragraph" class="value-row" :class="{ fail: !r.pass }">
          <div class="field-value">{{ r.actual_value || '(空)' }}</div>
          <div v-if="!r.pass" class="fail-reason">
            <el-icon><WarningFilled /></el-icon>
            {{ r.reason }}
          </div>
          <div v-else class="pass-indicator">
            <el-icon color="#67c23a"><CircleCheckFilled /></el-icon>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ValidateResult } from '../types'

const props = defineProps<{ result: ValidateResult }>()

const passCount = computed(() => props.result.results.filter(r => r.pass).length)
</script>

<style scoped>
.validation-container { height: 100%; }
.val-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
.dual-pane { display: flex; gap: 16px; }
.pane { flex: 1; border: 1px solid #e4e7ed; border-radius: 4px; padding: 16px; background: #fff; }
.pane h4 { margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #e4e7ed; }
.rule-row { padding: 8px 0; border-bottom: 1px dashed #e4e7ed; }
.value-row { padding: 8px 0; border-bottom: 1px dashed #e4e7ed; display: flex; align-items: center; justify-content: space-between; }
.value-row.fail { background: #fef0f0; }
.fail-reason { color: #f56c6c; font-size: 13px; }
.pass-indicator { color: #67c23a; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ValidationView.vue
git commit -m "feat: validation view component"
```

---

### Task 15: Review workbench page

**Files:**
- Create: `frontend/src/views/ReviewWorkbench.vue`

**Interfaces:**
- Consumes: all API functions from Task 10, `CompareDiffView` from Task 13, `ValidationView` from Task 14

- [ ] **Step 1: Write ReviewWorkbench.vue**

```vue
<template>
  <div class="review-page">
    <!-- Step 1: Upload and select -->
    <el-card v-if="!showResult">
      <template #header><span>审查工作台</span></template>
      <el-form label-width="100px">
        <el-form-item label="选择模板">
          <el-select v-model="selectedTemplateId" placeholder="请选择模板">
            <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="上传业务文件">
          <el-upload :show-file-list="false" :before-upload="handleDocUpload" accept=".docx">
            <el-button type="primary" :disabled="!selectedTemplateId">上传 docx</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item v-if="uploadedDoc" label="已上传文件">
          <el-tag>{{ uploadedDoc.name }}</el-tag>
        </el-form-item>
        <el-form-item label="审查流程">
          <el-radio-group v-model="reviewMode" :disabled="!uploadedDoc">
            <el-radio value="compare">防篡改比对</el-radio>
            <el-radio value="validate">数据校验</el-radio>
            <el-radio value="both">全部执行</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="startReview" :disabled="!uploadedDoc" :loading="reviewing">
            开始审查
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Step 2: Results -->
    <div v-if="showResult">
      <el-tabs v-model="activeTab">
        <el-tab-pane v-if="compareResult" label="防篡改比对" name="compare">
          <CompareDiffView :result="compareResult" />
        </el-tab-pane>
        <el-tab-pane v-if="validateResult" label="数据校验" name="validate">
          <ValidationView :result="validateResult" />
        </el-tab-pane>
      </el-tabs>
      <el-button type="default" @click="resetReview" style="margin-top: 16px">返回</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listTemplates, uploadDocument, reviewCompare, reviewValidate } from '../api'
import type { TemplateInfo, DocumentInfo, CompareResult, ValidateResult } from '../types'
import CompareDiffView from '../components/CompareDiffView.vue'
import ValidationView from '../components/ValidationView.vue'

const templates = ref<TemplateInfo[]>([])
const selectedTemplateId = ref<number | null>(null)
const uploadedDoc = ref<DocumentInfo | null>(null)
const reviewMode = ref<'compare' | 'validate' | 'both'>('compare')
const reviewing = ref(false)
const showResult = ref(false)
const activeTab = ref('compare')

const compareResult = ref<CompareResult | null>(null)
const validateResult = ref<ValidateResult | null>(null)

onMounted(async () => {
  templates.value = await listTemplates()
})

async function handleDocUpload(file: File) {
  if (!selectedTemplateId.value) return false
  uploadedDoc.value = await uploadDocument(file, selectedTemplateId.value)
  ElMessage.success('文件上传成功')
  return false
}

async function startReview() {
  if (!selectedTemplateId.value || !uploadedDoc.value) return
  reviewing.value = true
  const tid = selectedTemplateId.value
  const did = uploadedDoc.value.id

  if (reviewMode.value === 'compare' || reviewMode.value === 'both') {
    compareResult.value = await reviewCompare(tid, did)
  }
  if (reviewMode.value === 'validate' || reviewMode.value === 'both') {
    validateResult.value = await reviewValidate(tid, did)
  }

  activeTab.value = reviewMode.value === 'validate' ? 'validate' : 'compare'
  showResult.value = true
  reviewing.value = false
}

function resetReview() {
  showResult.value = false
  uploadedDoc.value = null
  compareResult.value = null
  validateResult.value = null
}
</script>
```

- [ ] **Step 2: Test full flow**

Start both backend and frontend. Go through: upload template → annotate → upload document → run review.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/ReviewWorkbench.vue
git commit -m "feat: review workbench page"
```

---

### Task 16: Integration test with real template

**Files:**
- Modify: none (test only)

- [ ] **Step 1: Start both services**

```bash
cd backend && uvicorn main:app --port 8000 &
cd frontend && npm run dev &
```

- [ ] **Step 2: Upload real template via API**

```bash
curl -X POST http://localhost:8000/api/templates/upload \
  -F "file=@docs/咨询服务标准合同-调整板V4.docx"
```

- [ ] **Step 3: Annotate the template**

Open http://localhost:5173 → click 标注 on the template → mark several paragraphs as fixed/fillable → configure rules → save.

- [ ] **Step 4: Upload test document and run review**

```bash
curl -X POST "http://localhost:8000/api/documents/upload?template_id=1" \
  -F "file=@docs/咨询服务标准合同-调整板V4-测试.docx"
```

Open http://localhost:5173/#/review → select template → upload document → run both review flows → verify results display correctly.

- [ ] **Step 5: Verify**

- [ ] Template annotation data persists (reload page, annotations still there)
- [ ] Tampering comparison shows character-level diff in Monaco Editor
- [ ] Data validation shows per-field pass/fail with rules
- [ ] Dual-pane views render correctly

- [ ] **Step 6: Commit**

```bash
git commit -m "test: integration verification with real template"
```

import os
import shutil
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, get_connection
from models import TemplateResponse, TemplateDetailResponse, ParagraphInfo
from services.parser import DocxParser

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

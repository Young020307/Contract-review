from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from middleware import IntegrationApiResponseMiddleware
from routers.templates import router as templates_router
from routers.documents import router as documents_router
from routers.review import router as review_router
from routers.integration import router as integration_router

app = FastAPI(
    title="审查模块统一集成 API (Review Gateway)",
    description="提供给主系统的黑盒调用接口，包含模板管理、文档上传、比对校验及一站式审查功能。",
    version="1.0.0",
    contact={
        "name": "合同审查团队",
        "email": "dev@example.com",
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(IntegrationApiResponseMiddleware)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/api/health")
def health():
    return {"status": "ok"}

app.include_router(templates_router)
app.include_router(documents_router)
app.include_router(review_router)

app.include_router(integration_router)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routers.templates import router as templates_router
from routers.documents import router as documents_router
from routers.review import router as review_router
from routers.integration import router as integration_router

app = FastAPI(title="合同智能审查系统 Demo")

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


app.include_router(templates_router)
app.include_router(documents_router)
app.include_router(review_router)
app.include_router(integration_router)

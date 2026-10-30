"""FastAPI 主入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import CORS_ORIGINS, UPLOAD_DIR
from database import init_db
from routers import admin, ai_analysis, ai_providers, articles, auth, chat_sessions, crawler, dashboard, keywords, profile, sources
from services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    await init_db()
    start_scheduler()
    print("[App] 系统已启动 → http://localhost:8000/docs")
    yield
    # 关闭
    stop_scheduler()
    print("[App] 系统已关闭")


app = FastAPI(
    title="策知 API",
    description="关键词驱动的政策资讯采集与 AI 分析平台",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(admin.router)
app.include_router(dashboard.router)
app.include_router(keywords.router)
app.include_router(sources.router)
app.include_router(crawler.router)
app.include_router(articles.router)
app.include_router(ai_providers.router)
app.include_router(ai_analysis.router)
app.include_router(chat_sessions.router)

# 静态文件服务（头像等上传文件）
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.get("/")
async def root():
    return {"message": "策知 · 行业资讯与政策智能分析平台 API", "docs": "/docs"}

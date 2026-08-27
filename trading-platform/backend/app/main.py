import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.routes import router
from app.config import settings
from app.engines.deploy_status import build_deploy_status
from app.workers.scheduler import setup_scheduler, stop_bots


@asynccontextmanager
async def lifespan(app: FastAPI):
  commit = settings.render_git_commit or os.environ.get("RENDER_GIT_COMMIT") or "unknown"
  print(f"[Startup] {settings.app_name} commit={commit[:12]} paper_only={settings.paper_trading_only}")
  await setup_scheduler()
  yield
  stop_bots()


app = FastAPI(
  title=settings.app_name,
  description="Multi-market paper trading platform with AI learning",
  version="1.0.0",
  lifespan=lifespan,
)

origins = [o.strip() for o in settings.cors_origins.split(",")]
app.add_middleware(
  CORSMiddleware,
  allow_origins=origins + ["*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
async def root():
  deploy = await build_deploy_status()
  dashboard = deploy.get("dashboard_url")
  return {
    "name": settings.app_name,
    "mode": "paper_trading" if settings.paper_trading_only else "live",
    "docs": "/docs",
    "api": "/api",
    "dashboard": dashboard,
    "dashboard_redirect": "/api/dashboard",
  }


@app.get("/dashboard", include_in_schema=False)
async def root_dashboard_redirect():
  deploy = await build_deploy_status()
  url = deploy.get("dashboard_url") or deploy.get("verified_dashboard_url")
  if not url:
    url = "https://apex-trading-dashboard-q1o1x9nlh-apexweb-adams-projects.vercel.app"
  return RedirectResponse(url=url, status_code=302)

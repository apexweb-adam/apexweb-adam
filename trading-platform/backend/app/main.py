import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.routes import router
from app.config import settings
from app.engines.deploy_status import build_deploy_status, recommended_dashboard_url
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
    "crm_landing": "/crm",
  }


@app.api_route("/dashboard", methods=["GET", "HEAD"], include_in_schema=False)
async def root_dashboard_redirect():
  url = await recommended_dashboard_url()
  return RedirectResponse(url=url, status_code=302)


@app.api_route("/crm", methods=["GET", "HEAD"], include_in_schema=False)
async def crm_landing():
  url = await recommended_dashboard_url()
  deploy = await build_deploy_status()
  stale = deploy.get("vercel_bundle_stale")
  promote_id = deploy.get("vercel_promote_deployment_id") or "dpl_DFWFJtVnsfSLAkby6DWNLqUHYX7p"
  html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="refresh" content="0;url={url}" />
  <title>Apex Trading CRM</title>
  <style>
    body {{ font-family: system-ui, sans-serif; background: #0a0a0f; color: #e5e5e5; padding: 2rem; }}
    a {{ color: #d4af37; }}
    .muted {{ color: #888; font-size: 0.9rem; margin-top: 1.5rem; }}
  </style>
</head>
<body>
  <h1>Apex Trading CRM</h1>
  <p>Redirecting to the live dashboard…</p>
  <p><a href="{url}">Open dashboard →</a></p>
  {"<p class='muted'>Production Vercel bundle is stale. Promote " + promote_id + " in Vercel when ready.</p>" if stale else ""}
  <p class="muted">Paper trading only · Real-time WebSocket · 4 autonomous bots</p>
</body>
</html>"""
  return HTMLResponse(content=html, status_code=200, headers={"Refresh": f"0; url={url}"})

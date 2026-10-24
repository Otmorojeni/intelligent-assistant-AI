"""FastAPI application entry point for CDO AI Assistant."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import check_document_compliance_endpoint, router as api_router
from src.config import settings

app = FastAPI(
    title="CDO AI Assistant API",
    description="Intelligent AI Assistant for Document Management, Approval Matrix routing and Regulatory QA.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for web frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include main API router
app.include_router(api_router)
app.add_api_route(
    "/v1/documents/check-compliance",
    check_document_compliance_endpoint,
    methods=["POST"],
    include_in_schema=False,
)

# Mount compiled React / Next.js static frontend bundle if present in ui/
if settings.STATIC_DIR.exists():
    if (settings.STATIC_DIR / "_next").exists():
        app.mount("/_next", StaticFiles(directory=str(settings.STATIC_DIR / "_next")), name="next_assets")
    if (settings.STATIC_DIR / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(settings.STATIC_DIR / "assets")), name="ui_assets")
    app.mount("/ui", StaticFiles(directory=str(settings.STATIC_DIR), html=True), name="ui_static")

    # Serve root static assets (favicon, logos, icons) directly from ui/
    for asset_name in ("favicon.png", "favicon.svg", "favicon.ico", "docorp-logo.png"):
        asset_file = settings.STATIC_DIR / asset_name
        if asset_file.exists():
            def _create_asset_handler(path=str(asset_file)):
                async def _handler():
                    return FileResponse(path)
                return _handler
            app.add_api_route(f"/{asset_name}", _create_asset_handler(), methods=["GET"], include_in_schema=False)



@app.get("/app", include_in_schema=False)
async def serve_spa_app():
    index_file = settings.STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"detail": "Frontend bundle not found in ui/index.html. Build React/Next.js into ui/."}


@app.get("/", tags=["Root"])
async def root(request: Request):
    index_file = settings.STATIC_DIR / "index.html"
    accept = request.headers.get("accept", "")
    if index_file.exists() and "text/html" in accept:
        return FileResponse(str(index_file))
    return {
        "service": "CDO AI Assistant",
        "status": "operational",
        "version": "1.0.0",
        "docs": "/docs",
    }

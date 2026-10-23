"""FastAPI application entry point for CDO AI Assistant."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router as api_router
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


@app.get("/", tags=["Root"])
async def root():
    return {
        "service": "CDO AI Assistant",
        "status": "operational",
        "version": "1.0.0",
        "docs": "/docs",
    }

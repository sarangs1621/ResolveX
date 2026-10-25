"""Vercel Serverless Function Entrypoint.

Exposes the FastAPI application to Vercel's Python runtime.
Ensures correct path resolution for serverless function invocations.
"""

import os
import sys
from pathlib import Path

# Ensure project root is at the head of sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Signal Vercel environment
os.environ.setdefault("VERCEL", "1")

try:
    from main import app
except Exception as exc:
    import traceback
    err_trace = traceback.format_exc()
    print(f"[VERCEL STARTUP EXCEPTION]:\n{err_trace}", file=sys.stderr)
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="ResolveX — Startup Diagnostic")

    @app.get("/{full_path:path}")
    def startup_error(full_path: str = ""):
        return JSONResponse(
            status_code=500,
            content={
                "status": "startup_failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": err_trace.splitlines()
            }
        )

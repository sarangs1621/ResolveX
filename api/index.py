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

# Import the ASGI FastAPI application
from main import app

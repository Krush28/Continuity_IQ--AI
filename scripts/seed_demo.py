"""Create demo users and the ShopEase demo project with the six sample documents uploaded.

Usage (from the repo root):  python scripts/seed_demo.py
Logins (password demo123):  manager@demo.in  ·  arjun@demo.in (outgoing member)  ·  karan@demo.in (incoming member)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.db import Base, engine  # noqa: E402
from app.demo import PROJECT_NAME, seed  # noqa: E402

Base.metadata.create_all(bind=engine)
if not seed(verbose=True):
    print(f"Demo project '{PROJECT_NAME}' already exists — nothing to do.")

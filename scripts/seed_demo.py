"""Create demo users and the ShopEase demo project with the six sample documents uploaded.

Usage (from the repo root):  python scripts/seed_demo.py
Logins (password demo123):  manager@demo.in  ·  arjun@demo.in (outgoing member)  ·  karan@demo.in (incoming member)
"""
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.auth import hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.llm import LLM  # noqa: E402
from app.models import Document, Project, ProjectMember, User  # noqa: E402
from app.pipeline import process_document  # noqa: E402

Base.metadata.create_all(bind=engine)
db = SessionLocal()


def user(name, email, role):
    u = db.query(User).filter_by(email=email).first()
    if not u:
        u = User(name=name, email=email, password_hash=hash_password("demo123"), role=role)
        db.add(u)
        db.flush()
    return u


mgr = user("Priya Nair", "manager@demo.in", "manager")
arjun = user("Arjun Mehta", "arjun@demo.in", "member")
karan = user("Karan Shah", "karan@demo.in", "incoming")

name = "ShopEase Order Management"
if db.query(Project).filter_by(name=name).first():
    print(f"Demo project '{name}' already exists — nothing to do.")
    sys.exit(0)

p = Project(name=name, owner_id=mgr.id,
            description="Order, inventory and delivery management web app for a Pune retail client. Arjun Mehta is leaving; Karan Shah takes over.")
db.add(p)
db.flush()
for u, r in ((mgr, "manager"), (arjun, "member"), (karan, "incoming")):
    db.add(ProjectMember(project_id=p.id, user_id=u.id, project_role=r))

llm = LLM.from_db(db)
folder = settings.UPLOAD_DIR / str(p.id)
folder.mkdir(parents=True, exist_ok=True)
for f in sorted((ROOT / "sample_docs").iterdir()):
    dest = folder / f"{uuid.uuid4().hex[:8]}_{f.name}"
    shutil.copy(f, dest)
    d = Document(project_id=p.id, filename=f.name, stored_path=str(dest), file_type=f.suffix[1:],
                 size_bytes=f.stat().st_size, uploaded_by=arjun.id)
    db.add(d)
    db.flush()
    stats = process_document(db, d, llm, arjun.id)
    print(f"  {f.name:32} → {stats['records']} records ({stats.get('engine', 'rules')})")
db.commit()
print(f"\nDemo ready. Engine: {llm.label}. Sign in as manager@demo.in / demo123")

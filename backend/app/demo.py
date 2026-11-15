"""Demo data: three users and the ShopEase project with the six sample documents.

Used by scripts/seed_demo.py and, when SEED_DEMO=true, automatically at server start
(so a hosted demo with a temporary disk always comes up ready to use).
"""
import shutil
import uuid

from .auth import hash_password
from .config import BASE_DIR, settings
from .db import SessionLocal
from .llm import LLM
from .models import Document, Project, ProjectMember, User
from .pipeline import process_document

SAMPLES = BASE_DIR.parent / "sample_docs"
PROJECT_NAME = "ShopEase Order Management"


def seed(verbose: bool = False) -> bool:
    db = SessionLocal()
    try:
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
        if db.query(Project).filter_by(name=PROJECT_NAME).first():
            db.commit()
            return False
        p = Project(name=PROJECT_NAME, owner_id=mgr.id,
                    description="Order, inventory and delivery management web app for a Pune retail client. Arjun Mehta is leaving; Karan Shah takes over.")
        db.add(p)
        db.flush()
        for u, r in ((mgr, "manager"), (arjun, "member"), (karan, "incoming")):
            db.add(ProjectMember(project_id=p.id, user_id=u.id, project_role=r))
        llm = LLM.from_db(db)
        folder = settings.UPLOAD_DIR / str(p.id)
        folder.mkdir(parents=True, exist_ok=True)
        for f in sorted(SAMPLES.iterdir()):
            dest = folder / f"{uuid.uuid4().hex[:8]}_{f.name}"
            shutil.copy(f, dest)
            d = Document(project_id=p.id, filename=f.name, stored_path=str(dest), file_type=f.suffix[1:],
                         size_bytes=f.stat().st_size, uploaded_by=arjun.id)
            db.add(d)
            db.flush()
            stats = process_document(db, d, llm, arjun.id)
            if verbose:
                print(f"  {f.name:32} → {stats['records']} records ({stats.get('engine', 'rules')})")
        db.commit()
        if verbose:
            print(f"\nDemo ready. Engine: {llm.label}. Sign in as manager@demo.in / demo123")
        return True
    finally:
        db.close()

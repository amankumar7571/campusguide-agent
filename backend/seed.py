"""Seed data: SAMPLE placement stats + default admin user.

All placement rows are clearly labelled sample data (is_sample=True).
Default admin: admin@campus.local / admin123 — change on first deploy.
"""
from .auth import hash_password
from .db import PlacementStat, SessionLocal, User, init_db
from .ingest import ingest_documents

SAMPLE_PLACEMENTS = [
    # company, year, role, offers, ctc_lpa — SAMPLE data, not real figures.
    ("SampleTech Solutions", 2025, "Software Engineer", 12, 6.5),
    ("SampleTech Solutions", 2024, "Software Engineer", 9, 6.0),
    ("NorthStar Analytics", 2025, "Data Analyst", 8, 5.5),
    ("NorthStar Analytics", 2025, "ML Engineer", 4, 7.0),
    ("CloudNine Systems", 2025, "Cloud Engineer", 6, 6.0),
    ("CloudNine Systems", 2024, "DevOps Engineer", 5, 5.8),
    ("BrightBank Fintech", 2025, "Backend Developer", 7, 7.5),
    ("BrightBank Fintech", 2024, "QA Engineer", 3, 4.5),
    ("EduSpark Labs", 2025, "Full Stack Developer", 10, 5.0),
    ("EduSpark Labs", 2024, "Full Stack Developer", 6, 4.8),
    ("GreenEnergy Corp", 2025, "IoT Engineer", 2, 5.2),
    ("MediCore Health", 2025, "Data Engineer", 5, 6.2),
]


def seed():
    init_db()
    db = SessionLocal()
    try:
        if db.query(PlacementStat).count() == 0:
            for company, year, role, offers, ctc in SAMPLE_PLACEMENTS:
                db.add(PlacementStat(company=company, year=year, role=role,
                                     offers=offers, ctc_lpa=ctc, is_sample=True))
        if not db.query(User).filter(User.email == "admin@campus.local").first():
            db.add(User(email="admin@campus.local",
                        password_hash=hash_password("admin123"), role="admin"))
        db.commit()
    finally:
        db.close()
    counts = ingest_documents()
    return counts


if __name__ == "__main__":
    print(seed())

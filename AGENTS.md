# AGENTS.md — Project Engineering Rules

## Project: Mission Readiness & Predictive Maintenance Copilot

This file is the authoritative engineering guide for all AI agents working on this codebase.
Read it before making any changes. Follow all rules without exception.

---

## 1. Source of Truth

- `plan.md` is the master specification. Never contradict it.
- The **database** is the analytics source of truth. The backend computes. The frontend displays.
- The **LLM (Gemini)** explains structured backend evidence. It never computes risk, health, or predictions.

---

## 2. Non-Negotiable Rules

- **No fake data.** Every chart, KPI, and visualization must consume real backend API data.
- **No hardcoded analytics.** No `risk_score = 0.87` or `asset = "NOT READY"` hardcoded anywhere.
- **No mock/SQLite.** PostgreSQL is mandatory. Never substitute SQLite for production.
- **No placeholder UI.** No buttons that do nothing. No "coming soon" pages for core features.
- **No secrets in frontend.** `GEMINI_API_KEY` and `DATABASE_URL` are backend-only.
- **No `.env` committed.** Only `.env.example` is committed.

---

## 3. Technology Stack

### Backend
- Python 3.11+
- FastAPI + Pydantic v2
- SQLAlchemy 2.x (async where beneficial)
- Alembic (migrations)
- pandas, NumPy, SciPy, scikit-learn
- joblib (model persistence)
- psycopg (psycopg3) driver for PostgreSQL

### Frontend
- React 18 + TypeScript
- Vite
- Tailwind CSS
- Recharts (primary chart library)

### Database
- PostgreSQL (local, `postgresql+psycopg://...`)

---

## 4. Project Structure

```
project-root/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers
│   │   ├── core/         # config, security, settings
│   │   ├── db/           # session, base, engine
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── schemas/      # Pydantic schemas
│   │   ├── services/     # business logic
│   │   ├── analytics/    # feature engineering, anomaly detection, risk
│   │   ├── ml/           # ML models, training, inference
│   │   ├── ingestion/    # CSV ingestion, validation
│   │   ├── copilot/      # Gemini integration + deterministic fallback
│   │   └── main.py
│   ├── alembic/
│   ├── tests/
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── charts/
│   │   ├── services/     # API clients
│   │   ├── hooks/
│   │   ├── types/
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
├── data/
│   ├── synthetic/
│   └── samples/
├── scripts/              # standalone utility scripts
├── docs/
├── .env.example
├── .gitignore
├── AGENTS.md             (this file)
├── README.md
├── ARCHITECTURE.md
├── DATA_DICTIONARY.md
├── MODEL_CARD.md
├── SECURITY.md
├── DEMO.md
└── plan.md
```

---

## 5. Database Schema Entities

Asset, Component, SensorReading, MaintenanceRecord, AnomalyEvent, Prediction,
ReadinessAssessment, MaintenanceRecommendation, DataQualityReport, AuditLog

Use UUIDs as primary keys. All entities include `created_at` / `updated_at` timestamps.

---

## 6. Environment Variables

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/hums_db
GEMINI_API_KEY=
SECRET_KEY=
ENVIRONMENT=development
```

---

## 7. Code Quality Rules

- Type hints everywhere in Python
- Pydantic v2 models for all API schemas
- Modular architecture — no giant files
- Meaningful names — no single-letter variables outside math loops
- Separation of concerns — routers call services, services call analytics, analytics call models
- All DB operations through SQLAlchemy ORM (no raw SQL unless unavoidable)
- Migrations via Alembic only — never `Base.metadata.create_all()` in production paths

---

## 8. Testing Rules

- Tests live in `backend/tests/`
- Use pytest
- Test actual logic, not just HTTP 200
- Cover: models, ingestion, data quality, feature engineering, anomaly detection, risk, readiness, APIs

---

## 9. Frontend Rules

- Both Light Mode and Dark Mode are required and fully functional
- Theme toggle persists via localStorage
- All charts adapt to both themes using centralized theme tokens
- No hardcoded chart data — all from backend API
- Cross-filtering between visualizations is required

---

## 10. Safety

The application is strictly a maintenance/reliability decision-support tool.
It must never provide targeting, weapon, or combat recommendations.
Every AI recommendation must display: "AI-generated maintenance recommendations are decision-support outputs. Final readiness and maintenance decisions require qualified human review."

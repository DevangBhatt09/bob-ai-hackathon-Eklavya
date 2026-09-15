# 🚀 Mission Readiness & Predictive Maintenance Copilot

> ⚠️ **Replace everything in `[ ]` brackets with your actual content before submission.**

---

## 👥 Team

| Field | Value |
|---|---|
| **Team Name** | Eklavya |
| **Track** | Sustainability |
| **Team Lead** | Hitansh Parikh — 23cs054@charusat.edu.in |
| **Members** | Devang Bhatt, Pankti Akbari, Gunja Bhatt |

---

## 🎯 Problem Statement

> In 2–3 sentences: What problem does your project solve? Who experiences this problem?

Fleet maintenance teams often work with fragmented sensor, maintenance, and component data, making it difficult to detect early failures and determine whether an asset is ready for operation. Maintenance engineers, technicians, supervisors, and reliability analysts need an evidence-based way to identify anomalies, estimate component risk, and prioritize maintenance.

---

## 💡 Solution

> In 2–3 sentences: What did you build? How does it solve the problem above?

HUMS is a mission-readiness and predictive-maintenance platform that ingests sensor and maintenance records into PostgreSQL and analyzes them through anomaly detection, feature engineering, risk prediction, data-quality assessment, and readiness evaluation. A React dashboard presents the results, while a Gemini-powered copilot explains maintenance evidence and recommendations for qualified human review.

---

## ✨ Key Features

- **Feature 1:** Fleet Dashboard: Displays fleet health, readiness distribution, risk levels, anomalies, and maintenance indicators.
- **Feature 2:** Anomaly Detection: Uses rolling z-scores, IQR analysis, and Isolation Forest detection on sensor readings.
- **Feature 3:** Predictive Maintenance: Estimates component failure risk using maintenance history, sensor trends, thresholds, utilization, and anomaly evidence.
- **Feature 4:** Readiness Assessment: Classifies assets as READY, READY_WITH_CAUTION, MAINTENANCE_REQUIRED, NOT_READY, or INSUFFICIENT_DATA.
- **Feature 5:** AI Copilot: Provides RAG-based maintenance explanations using Gemini and asset context.

---

## 🛠️ Tech Stack

| Category | Technologies |
|---|---|
| **Languages** | Python 3.11+, TypeScript, JavaScript, SQL |
| **Frameworks** | FastAPI, React 18, Vite, Tailwind CSS |
| **IBM Technologies** | IBM Bob |
| **Databases** | PostgreSQL with SQLAlchemy and psycopg3 |
| **Other** | Uvicorn, Pydantic, python-dotenv, HTTPX |

---

## 📁 Repository Structure

```
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routes
│   │   ├── analytics/    # Anomaly, risk, readiness, and prioritization logic
│   │   ├── copilot/      # Gemini and retrieval support
│   │   ├── core/         # Configuration
│   │   ├── db/           # Database session and base
│   │   ├── ingestion/    # CSV validation and ingestion
│   │   └── models/       # SQLAlchemy models
│   ├── alembic/          # Database migrations
│   ├── tests/            # Backend tests
│   ├── requirements.txt
│   └── run_pipeline.py
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── types/
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
├── scripts/
│   └── generate_synthetic_data.py
├── .env.example
├── AGENTS.md
├── README.md
└── LICENSE
```

---

## ⚡ How to Run

> **Copy these exact steps from your [`docs/setup-guide.md`](docs/setup-guide.md)**

```bash
# 1. Install and configure PostgreSQL first
# Create the hums_user user and hums_db database

# 2. Set up the backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Configure environment
copy ..\.env.example .env
# Edit .env with DATABASE_URL and optionally GEMINI_API_KEY

# 4. Run database migrations
python -m alembic upgrade head

# 5. Generate reproducible synthetic data
python ..\scripts\generate_synthetic_data.py --assets 55

# 6. Run the analytics pipeline
python run_pipeline.py

# 7. Start the backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

In a second terminal :
cd frontend
npm install
npm run dev
```

---

## 🖥️ Demo

| Artifact | Link |
|---|---|
| 📹 Demo Video | https://drive.google.com/file/d/1xNLQpL2Lobhq1cF0k7_vCGqRIpd2G4oZ/view?usp=sharing |
| 📊 Presentation | https://docs.google.com/presentation/d/1eysU2AZtMssn8QIYc4dE0ez4_4ygXF1j/edit?usp=sharing&ouid=107847315468194521352&rtpof=true&sd=true |

---

## ⚠️ Known Limitations

> Be honest — judges appreciate transparency over overclaiming.

- Current backend verification produced 120 passed and 4 failed tests. The failures involve UUID binding and persistence behavior in SQLite test fixtures.
- Authentication and authorization are not implemented in the visible application routes.
- Copilot conversation history is process-local and is not persisted in PostgreSQL.

---

## 🏅 What We're Most Proud Of

The strongest part of HUMS is its end-to-end, evidence-based maintenance workflow. Sensor anomalies, data quality, component risk, readiness status, and maintenance priority are connected into one explainable process, while insufficient data is treated explicitly instead of being presented as a false indication of readiness. Every AI-generated recommendation includes a qualified-human-review requirement.

---

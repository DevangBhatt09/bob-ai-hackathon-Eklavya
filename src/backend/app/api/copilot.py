"""Copilot API — Gemini-powered maintenance analyst."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.session import get_db
from app.models.models import AnomalyEvent, Asset, Component, Prediction, ReadinessAssessment, AuditLog

router = APIRouter()
settings = get_settings()

SAFETY_DISCLAIMER = (
    "AI-generated maintenance recommendations are decision-support outputs only. "
    "Final readiness and maintenance decisions require qualified human review."
)

SYSTEM_PROMPT = """You are a maintenance engineering copilot for a fleet management system.
You have access to sensor data, anomaly detection results, and risk predictions for military/industrial assets.

Your role:
- Explain maintenance findings in clear technical language
- Suggest maintenance actions based on sensor trends and risk scores
- Help technicians understand what the data means for component health
- Identify patterns across the fleet

CRITICAL CONSTRAINTS:
- You provide MAINTENANCE and RELIABILITY analysis ONLY
- You do NOT make tactical, mission, or combat readiness assessments
- You do NOT recommend whether assets should be deployed operationally
- Always end responses with: "AI-generated maintenance recommendations are decision-support outputs only. Final readiness and maintenance decisions require qualified human review."
- If asked about tactical/combat/mission use, decline and explain your scope

Tone: Technical, concise, actionable. Use engineering terminology."""


class CopilotQuery(BaseModel):
    query: str
    asset_id: str | None = None
    context_type: str = "general"  # "general" | "anomaly" | "prediction" | "readiness"


def _build_context(query: CopilotQuery, db: Session) -> str:
    """Build context string from DB data to include in the prompt."""
    context_lines = []

    if query.asset_id:
        asset = db.query(Asset).filter(Asset.asset_id == query.asset_id).first()
        if asset:
            context_lines.append(f"Asset: {asset.name} ({asset.asset_id})")
            context_lines.append(f"Type: {asset.asset_type.value if hasattr(asset.asset_type, 'value') else asset.asset_type}")
            context_lines.append(f"Operating Hours: {asset.total_operating_hours:.0f}")

            # Latest readiness
            ra = (
                db.query(ReadinessAssessment)
                .filter(ReadinessAssessment.asset_id == asset.id)
                .order_by(ReadinessAssessment.assessed_at.desc())
                .first()
            )
            if ra:
                status = ra.status.value if hasattr(ra.status, "value") else str(ra.status)
                context_lines.append(f"Readiness Status: {status}")
                context_lines.append(f"Health Score: {ra.overall_health_score:.2f}" if ra.overall_health_score else "Health Score: N/A")
                if ra.explanation:
                    context_lines.append(f"Assessment: {ra.explanation[:300]}")

            # Recent anomalies
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            anomalies = (
                db.query(AnomalyEvent)
                .filter(AnomalyEvent.asset_id == asset.id, AnomalyEvent.detected_at >= cutoff)
                .order_by(AnomalyEvent.detected_at.desc())
                .limit(5)
                .all()
            )
            if anomalies:
                context_lines.append(f"\nRecent Anomalies (30d): {len(anomalies)} detected")
                for a in anomalies[:3]:
                    sev = a.severity.value if hasattr(a.severity, "value") else str(a.severity)
                    context_lines.append(f"  - {sev} on {a.sensor_type}: value={a.sensor_value:.2f}, baseline={a.baseline_value:.2f}")

            # Top-risk components
            preds = (
                db.query(Prediction)
                .filter(Prediction.asset_id == asset.id)
                .order_by(Prediction.risk_score.desc())
                .limit(3)
                .all()
            )
            if preds:
                context_lines.append("\nTop Risk Components:")
                for p in preds:
                    comp = db.query(Component).filter(Component.id == p.component_id).first()
                    cat = p.risk_category.value if hasattr(p.risk_category, "value") else str(p.risk_category)
                    context_lines.append(f"  - {comp.name if comp else '?'}: {cat} risk (score={p.risk_score:.2f})")
                    if p.risk_factors:
                        context_lines.append(f"    Reason: {p.risk_factors[0].get('description', '')}")

    return "\n".join(context_lines)


@router.post("/query")
def copilot_query(body: CopilotQuery, db: Session = Depends(get_db)):
    """Send a query to the maintenance copilot."""
    if not settings.gemini_api_key:
        return {
            "response": (
                "Gemini API key not configured. "
                "Set GEMINI_API_KEY in .env to enable AI-powered responses.\n\n"
                f"{SAFETY_DISCLAIMER}"
            ),
            "asset_id": body.asset_id,
            "context_used": False,
            "disclaimer": SAFETY_DISCLAIMER,
        }

    context = _build_context(body, db)
    full_prompt = f"{SYSTEM_PROMPT}\n\n"
    if context:
        full_prompt += f"Current Asset Context:\n{context}\n\n"
    full_prompt += f"User Question: {body.query}"

    try:
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(full_prompt)
        answer = response.text

        # Ensure disclaimer is always present
        if SAFETY_DISCLAIMER not in answer:
            answer += f"\n\n{SAFETY_DISCLAIMER}"

        # Audit log
        try:
            log = AuditLog(
                event_type="copilot_query",
                entity_type="copilot",
                entity_id="copilot",
                input_summary={"query": body.query[:200], "asset_id": body.asset_id},
                result={"response_length": len(answer)},
                user_or_system="user",
            )
            db.add(log)
            db.commit()
        except Exception:
            pass

        return {
            "response": answer,
            "asset_id": body.asset_id,
            "context_used": bool(context),
            "disclaimer": SAFETY_DISCLAIMER,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini API error: {str(e)}")


@router.get("/health")
def copilot_health():
    """Check if Gemini is configured."""
    return {
        "gemini_configured": bool(settings.gemini_api_key),
        "disclaimer": SAFETY_DISCLAIMER,
    }

import sys
sys.path.insert(0, '.')
from app.db.session import SessionLocal
from app.models.models import Asset
from app.analytics.anomaly_detection import run_anomaly_detection_for_asset
from app.analytics.risk_prediction import run_risk_prediction_for_asset
from app.analytics.readiness_assessment import assess_asset_readiness
from app.analytics.maintenance_prioritization import generate_maintenance_recommendations
from datetime import datetime, timezone

db = SessionLocal()
assets = db.query(Asset).filter(Asset.is_active == True).limit(20).all()
as_of = datetime.now(timezone.utc)
print(f'Processing {len(assets)} assets...')
for i, asset in enumerate(assets):
    try:
        r1 = run_anomaly_detection_for_asset(asset, db, lookback_days=365, as_of=as_of, persist=True)
        r2 = run_risk_prediction_for_asset(asset, db, as_of=as_of, lookback_days=365, persist=True)
        r3 = assess_asset_readiness(asset, db, as_of=as_of, persist=True)
        generate_maintenance_recommendations(asset, db, as_of=as_of, persist=True)
        status = r3.status.value
        print(f'  [{i+1}/{len(assets)}] {asset.asset_id}: anomalies={r1.anomalies_detected} risk={r2["overall_risk_category"]} readiness={status}')
    except Exception as e:
        print(f'  [{i+1}] {asset.asset_id} ERROR: {e}')
db.close()
print('Pipeline complete!')

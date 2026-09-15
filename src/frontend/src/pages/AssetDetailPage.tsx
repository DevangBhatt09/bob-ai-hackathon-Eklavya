import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getAsset, getAssetSensorHistory, listAnomalies, listPredictions, getAssetReadiness } from '../services/api';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { useTheme } from '../hooks/useTheme';

const RISK_COLORS: Record<string, string> = { CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#eab308', LOW: '#22c55e' };
const READINESS_COLORS: Record<string, string> = { READY: '#22c55e', READY_WITH_CAUTION: '#eab308', MAINTENANCE_REQUIRED: '#f97316', NOT_READY: '#ef4444', INSUFFICIENT_DATA: '#94a3b8' };

export default function AssetDetailPage() {
  const { assetId } = useParams<{ assetId: string }>();
  const { theme } = useTheme();
  const [asset, setAsset] = useState<any>(null);
  const [sensorHistory, setSensorHistory] = useState<any[]>([]);
  const [anomalies, setAnomalies] = useState<any[]>([]);
  const [predictions, setPredictions] = useState<any[]>([]);
  const [readiness, setReadiness] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selectedSensor, setSelectedSensor] = useState('temperature');

  const bg = theme === 'dark' ? '#1f2937' : '#ffffff';
  const textColor = theme === 'dark' ? '#e5e7eb' : '#374151';
  const gridColor = theme === 'dark' ? '#374151' : '#e5e7eb';

  useEffect(() => {
    if (!assetId) return;
    Promise.all([
      getAsset(assetId),
      getAssetSensorHistory(assetId, { sensor_type: selectedSensor, days: 90 }),
      listAnomalies({ asset_id: assetId, days: 365, limit: 20 }),
      listPredictions({ asset_id: assetId, limit: 20 }),
      getAssetReadiness(assetId),
    ]).then(([a, sh, an, pr, rd]) => {
      setAsset(a);
      setSensorHistory(sh.readings || []);
      setAnomalies(an.items || []);
      setPredictions(pr.items || []);
      setReadiness(rd);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [assetId]);

  useEffect(() => {
    if (!assetId || loading) return;
    getAssetSensorHistory(assetId, { sensor_type: selectedSensor, days: 90 })
      .then(sh => setSensorHistory(sh.readings || []))
      .catch(() => {});
  }, [selectedSensor]);

  if (loading) return <div className="p-6 text-center text-gray-500">Loading asset details...</div>;
  if (!asset) return <div className="p-6 text-red-500">Asset not found</div>;

  const status = readiness?.status;
  const statusColor = READINESS_COLORS[status] || '#94a3b8';

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold dark:text-white">{asset.asset_id}</h1>
            <span className="text-sm px-3 py-1 rounded-full font-medium" style={{ background: statusColor + '20', color: statusColor }}>
              {status || 'No Assessment'}
            </span>
          </div>
          <p className="text-sm text-gray-500 mt-1">{asset.name} · {asset.asset_type} · {asset.fleet}</p>
        </div>
        <div className="text-right">
          <div className="text-sm text-gray-500">Health Score</div>
          <div className="text-2xl font-bold" style={{ color: statusColor }}>
            {readiness?.overall_health_score != null ? `${(readiness.overall_health_score * 100).toFixed(0)}%` : 'N/A'}
          </div>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Operating Hours', value: asset.total_operating_hours?.toFixed(0) + ' hrs' },
          { label: 'Total Cycles', value: asset.total_cycles?.toLocaleString() },
          { label: 'Components', value: asset.components?.length || 0 },
          { label: 'Location', value: asset.location || '—' },
        ].map(({ label, value }) => (
          <div key={label} className={`rounded-xl p-4 border ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
            <div className="text-xs text-gray-500">{label}</div>
            <div className="text-lg font-semibold dark:text-white mt-0.5">{value}</div>
          </div>
        ))}
      </div>

      {/* Components Risk Table */}
      <div className={`rounded-xl border p-5 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
        <h2 className="text-base font-semibold mb-3 dark:text-white">Component Health Profile</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className={`border-b ${theme === 'dark' ? 'border-gray-700' : 'border-gray-200'}`}>
              {['Component', 'Type', 'Criticality', 'Op. Hours', 'Life Used', 'Risk Score', 'Risk Level'].map(h => (
                <th key={h} className="text-left py-2 px-2 text-xs font-medium text-gray-500">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(asset.components || []).map((comp: any) => (
              <tr key={comp.id} className={`border-b ${theme === 'dark' ? 'border-gray-700' : 'border-gray-100'}`}>
                <td className="py-2 px-2 font-medium dark:text-white text-xs">{comp.name}</td>
                <td className="py-2 px-2 text-gray-500 text-xs">{comp.component_type}</td>
                <td className="py-2 px-2 text-xs"><span className={`px-1.5 py-0.5 rounded text-xs ${comp.criticality === 'HIGH' ? 'bg-red-100 text-red-600' : 'bg-gray-100 text-gray-600'}`}>{comp.criticality}</span></td>
                <td className="py-2 px-2 text-gray-500 text-xs">{comp.current_operating_hours?.toFixed(0) || '—'}</td>
                <td className="py-2 px-2 text-xs">
                  {comp.life_utilisation != null ? (
                    <div className="flex items-center gap-1">
                      <div className="w-12 h-1.5 bg-gray-200 rounded-full"><div className="h-full rounded-full" style={{ width: `${Math.min(100, comp.life_utilisation * 100)}%`, background: comp.life_utilisation > 0.8 ? '#ef4444' : comp.life_utilisation > 0.5 ? '#eab308' : '#22c55e' }} /></div>
                      <span className="text-gray-500">{(comp.life_utilisation * 100).toFixed(0)}%</span>
                    </div>
                  ) : '—'}
                </td>
                <td className="py-2 px-2 text-xs">{comp.risk_score != null ? `${(comp.risk_score * 100).toFixed(0)}%` : '—'}</td>
                <td className="py-2 px-2 text-xs">
                  {comp.risk_category && <span className="font-medium" style={{ color: RISK_COLORS[comp.risk_category] }}>{comp.risk_category}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Sensor History Chart */}
      <div className={`rounded-xl border p-5 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold dark:text-white">Degradation Timeline</h2>
          <select className={`text-sm px-2 py-1 rounded border ${theme === 'dark' ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'}`}
            value={selectedSensor} onChange={e => setSelectedSensor(e.target.value)}>
            {['temperature', 'vibration', 'pressure', 'rpm'].map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        {sensorHistory.length === 0 ? (
          <div className="text-center text-gray-400 py-8">No sensor data available</div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={sensorHistory.slice(0, 500)} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
              <XAxis dataKey="timestamp" tick={{ fill: textColor, fontSize: 10 }} tickFormatter={v => v?.slice(5, 10)} />
              <YAxis tick={{ fill: textColor, fontSize: 11 }} />
              <Tooltip contentStyle={{ background: bg, color: textColor, border: `1px solid ${gridColor}` }} labelFormatter={v => String(v ?? '').slice(0, 16)} />
              <Line type="monotone" dataKey="sensor_value" stroke="#3b82f6" dot={false} strokeWidth={1.5} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Recent Anomalies */}
      <div className={`rounded-xl border p-5 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
        <h2 className="text-base font-semibold mb-3 dark:text-white">Recent Anomalies</h2>
        {anomalies.length === 0 ? <div className="text-gray-400 text-sm">No anomalies detected</div> : (
          <div className="space-y-2">
            {anomalies.map((a: any) => (
              <div key={a.id} className={`flex items-center gap-3 p-2 rounded-lg ${theme === 'dark' ? 'bg-gray-700' : 'bg-gray-50'}`}>
                <span className="text-xs font-medium px-2 py-0.5 rounded" style={{ background: RISK_COLORS[a.severity] + '20', color: RISK_COLORS[a.severity] }}>{a.severity}</span>
                <span className="text-xs text-gray-500">{a.sensor_type}</span>
                <span className="text-xs dark:text-white">value: {a.sensor_value?.toFixed(2)} (baseline: {a.baseline_value?.toFixed(2)})</span>
                <span className="text-xs text-gray-400 ml-auto">{a.detected_at?.slice(0, 10)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

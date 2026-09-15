import { useEffect, useState } from 'react';
import { listPredictions, getFailureRiskHorizon, listMaintenance, updateMaintenanceReview } from '../services/api';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { useTheme } from '../hooks/useTheme';

const RISK_COLORS: Record<string, string> = { CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#eab308', LOW: '#22c55e' };
const PRIORITY_COLORS: Record<string, string> = { IMMEDIATE: '#ef4444', HIGH: '#f97316', PLANNED: '#eab308', MONITOR: '#22c55e' };

export default function PredictiveMaintPage() {
  const { theme } = useTheme();
  const [horizon, setHorizon] = useState<any[]>([]);
  const [maintenance, setMaintenance] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'horizon' | 'board'>('horizon');
  const [loading, setLoading] = useState(true);

  const bg = theme === 'dark' ? '#1f2937' : '#ffffff';
  const textColor = theme === 'dark' ? '#e5e7eb' : '#374151';
  const gridColor = theme === 'dark' ? '#374151' : '#e5e7eb';

  useEffect(() => {
    Promise.all([getFailureRiskHorizon(20), listMaintenance({ limit: 50 })])
      .then(([h, m]) => { setHorizon(h.horizon || []); setMaintenance(m.items || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const handleReview = async (id: string, status: string) => {
    await updateMaintenanceReview(id, { review_status: status, reviewed_by: 'Analyst' });
    setMaintenance(prev => prev.map(r => r.id === id ? { ...r, review_status: status } : r));
  };

  if (loading) return <div className="p-6 text-center text-gray-500">Loading predictive maintenance data...</div>;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold dark:text-white">Predictive Maintenance Command Center</h1>

      {/* Tabs */}
      <div className="flex gap-2">
        {(['horizon', 'board'] as const).map(t => (
          <button key={t} onClick={() => setActiveTab(t)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${activeTab === t ? 'bg-blue-600 text-white' : theme === 'dark' ? 'bg-gray-700 text-gray-300' : 'bg-gray-100 text-gray-600'}`}>
            {t === 'horizon' ? 'Failure-Risk Horizon' : 'Maintenance Priority Board'}
          </button>
        ))}
      </div>

      {activeTab === 'horizon' && (
        <div className={`rounded-xl border p-5 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
          <h2 className="text-base font-semibold mb-4 dark:text-white">Top 20 Components by Failure Risk</h2>
          {horizon.length === 0 ? <div className="text-center text-gray-400 py-12">No prediction data — run pipeline first</div> : (
            <>
              <ResponsiveContainer width="100%" height={400}>
                <BarChart data={horizon} layout="vertical" margin={{ left: 180, right: 40, top: 5, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={gridColor} horizontal={false} />
                  <XAxis type="number" domain={[0, 1]} tick={{ fill: textColor, fontSize: 11 }} tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
                  <YAxis type="category" dataKey="component_name" tick={{ fill: textColor, fontSize: 11 }} width={175} />
                  <Tooltip contentStyle={{ background: bg, color: textColor, border: `1px solid ${gridColor}` }}
                    formatter={(v: any, _, props: any) => [`${(Number(v) * 100).toFixed(1)}% — ${props.payload.risk_category}`, 'Risk Score']} />
                  <Bar dataKey="risk_score" radius={[0, 4, 4, 0]}>
                    {horizon.map(e => <Cell key={e.component_id} fill={RISK_COLORS[e.risk_category] || '#94a3b8'} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="text-xs text-center text-gray-400 mt-2">AI-generated maintenance recommendations are decision-support outputs only. Final decisions require qualified human review.</p>
            </>
          )}
        </div>
      )}

      {activeTab === 'board' && (
        <div className={`rounded-xl border p-5 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
          <h2 className="text-base font-semibold mb-4 dark:text-white">Maintenance Priority Board</h2>
          {maintenance.length === 0 ? <div className="text-center text-gray-400 py-12">No maintenance recommendations — run pipeline first</div> : (
            <div className="space-y-3">
              {maintenance.map((rec: any) => (
                <div key={rec.id} className={`rounded-lg border p-4 ${theme === 'dark' ? 'bg-gray-700 border-gray-600' : 'bg-gray-50 border-gray-200'}`}>
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold px-2 py-0.5 rounded" style={{ background: PRIORITY_COLORS[rec.priority] + '20', color: PRIORITY_COLORS[rec.priority] }}>{rec.priority}</span>
                      <span className="text-sm font-medium dark:text-white">{rec.issue_summary}</span>
                    </div>
                    <div className="flex gap-1 ml-4 flex-shrink-0">
                      {rec.review_status === 'PENDING' && (
                        <>
                          <button onClick={() => handleReview(rec.id, 'ACCEPTED')} className="text-xs px-2 py-1 bg-green-100 text-green-700 rounded hover:bg-green-200">Accept</button>
                          <button onClick={() => handleReview(rec.id, 'REJECTED')} className="text-xs px-2 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200">Reject</button>
                        </>
                      )}
                      {rec.review_status !== 'PENDING' && (
                        <span className={`text-xs px-2 py-0.5 rounded ${rec.review_status === 'ACCEPTED' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>{rec.review_status}</span>
                      )}
                    </div>
                  </div>
                  {rec.recommended_action && (
                    <p className="text-xs text-gray-500 mt-2 line-clamp-2">{rec.recommended_action?.split('\n')[0]}</p>
                  )}
                </div>
              ))}
            </div>
          )}
          <p className="text-xs text-center text-gray-400 mt-4">AI-generated maintenance recommendations are decision-support outputs only. Final decisions require qualified human review.</p>
        </div>
      )}
    </div>
  );
}

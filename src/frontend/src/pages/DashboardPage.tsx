import { useEffect, useState } from 'react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import { getDashboardSummary, getFleetHealthMatrix, getAnomalyTimeline, getFailureRiskHorizon } from '../services/api';
import { useTheme } from '../hooks/useTheme';

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#22c55e',
};
const RISK_COLORS: Record<string, string> = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#3b82f6',
};
const READINESS_COLORS: Record<string, string> = {
  READY: '#22c55e',
  READY_WITH_CAUTION: '#eab308',
  MAINTENANCE_REQUIRED: '#f97316',
  NOT_READY: '#ef4444',
  INSUFFICIENT_DATA: '#94a3b8',
};

function StatCard({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) {
  const { theme } = useTheme();
  return (
    <div className={`rounded-xl p-5 border ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} shadow-sm`}>
      <div className="text-sm font-medium text-gray-500 dark:text-gray-400">{label}</div>
      <div className={`text-3xl font-bold mt-1 ${color || 'text-gray-900 dark:text-white'}`}>{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-1">{sub}</div>}
    </div>
  );
}

export default function DashboardPage() {
  const { theme } = useTheme();
  const [summary, setSummary] = useState<any>(null);
  const [matrix, setMatrix] = useState<any>(null);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [horizon, setHorizon] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const bg = theme === 'dark' ? '#1f2937' : '#ffffff';
  const textColor = theme === 'dark' ? '#e5e7eb' : '#374151';
  const gridColor = theme === 'dark' ? '#374151' : '#e5e7eb';

  useEffect(() => {
    Promise.all([
      getDashboardSummary(),
      getFleetHealthMatrix(),
      getAnomalyTimeline(30),
      getFailureRiskHorizon(15),
    ])
      .then(([s, m, t, h]) => {
        setSummary(s);
        setMatrix(m);
        // Process timeline data
        const byDay: Record<string, Record<string, number>> = {};
        (t.timeline || []).forEach((row: any) => {
          const day = row.day?.split('T')[0];
          if (!day) return;
          if (!byDay[day]) byDay[day] = { day };
          byDay[day][row.severity] = (byDay[day][row.severity] || 0) + row.count;
        });
        setTimeline(Object.values(byDay).slice(-30));
        setHorizon(h.horizon || []);
        setLoading(false);
      })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64 text-gray-500">Loading dashboard data...</div>;
  if (error) return <div className="p-6 text-red-500">Error: {error}</div>;
  if (!summary) return null;

  // Readiness pie data
  const readinessPieData = Object.entries(summary.readiness_distribution || {}).map(([k, v]) => ({ name: k, value: v as number }));
  // Risk pie data
  const riskPieData = Object.entries(summary.risk_distribution || {}).map(([k, v]) => ({ name: k, value: v as number }));

  // Fleet Health Matrix — top 10 assets
  const matrixAssets = (matrix?.assets || []).slice(0, 10);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold dark:text-white">Fleet Operations Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">Real-time predictive maintenance overview</p>
        </div>
        {summary.pipeline_run_needed && (
          <div className="text-sm bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200 px-3 py-1.5 rounded-lg border border-yellow-300 dark:border-yellow-700">
            Pipeline not yet run — charts may show limited data
          </div>
        )}
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Total Assets" value={summary.fleet?.total_assets ?? '—'} sub={`${summary.fleet?.total_components ?? 0} components`} />
        <StatCard label="Sensor Readings" value={Number(summary.fleet?.total_sensor_readings ?? 0).toLocaleString()} sub="Historical dataset" />
        <StatCard
          label="Critical Alerts"
          value={summary.anomalies?.critical_unacknowledged ?? 0}
          sub="Unacknowledged"
          color={summary.anomalies?.critical_unacknowledged > 0 ? 'text-red-500' : 'text-green-500'}
        />
        <StatCard
          label="Fleet Health Score"
          value={summary.fleet_health_score != null ? `${(summary.fleet_health_score * 100).toFixed(1)}%` : 'N/A'}
          sub="Avg across assessed assets"
          color={summary.fleet_health_score > 0.7 ? 'text-green-500' : summary.fleet_health_score > 0.4 ? 'text-yellow-500' : 'text-red-500'}
        />
      </div>

      {/* Row 2: Readiness Distribution + Risk Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Readiness Status Pie */}
        <div className={`rounded-xl border p-5 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} shadow-sm`}>
          <h2 className="text-base font-semibold mb-4 dark:text-white">Fleet Readiness Distribution</h2>
          {readinessPieData.length === 0 ? (
            <div className="text-center text-gray-400 py-12">No readiness data — run pipeline first</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={readinessPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={({ name, value }) => `${name}: ${value}`} labelLine={false}>
                  {readinessPieData.map((entry) => (
                    <Cell key={entry.name} fill={READINESS_COLORS[entry.name] || '#94a3b8'} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: bg, color: textColor, border: `1px solid ${gridColor}` }} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Risk Distribution Pie */}
        <div className={`rounded-xl border p-5 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} shadow-sm`}>
          <h2 className="text-base font-semibold mb-4 dark:text-white">Component Risk Distribution</h2>
          {riskPieData.length === 0 ? (
            <div className="text-center text-gray-400 py-12">No prediction data — run pipeline first</div>
          ) : (
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={riskPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={({ name, value }) => `${name}: ${value}`} labelLine={false}>
                  {riskPieData.map((entry) => (
                    <Cell key={entry.name} fill={RISK_COLORS[entry.name] || '#94a3b8'} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: bg, color: textColor, border: `1px solid ${gridColor}` }} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Anomaly Timeline */}
      <div className={`rounded-xl border p-5 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} shadow-sm`}>
        <h2 className="text-base font-semibold mb-4 dark:text-white">Sensor Anomaly Timeline (30 days)</h2>
        {timeline.length === 0 ? (
          <div className="text-center text-gray-400 py-12">No anomaly data — run pipeline first</div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={timeline} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
              <XAxis dataKey="day" tick={{ fill: textColor, fontSize: 11 }} tickFormatter={v => v?.slice(5)} />
              <YAxis tick={{ fill: textColor, fontSize: 11 }} />
              <Tooltip contentStyle={{ background: bg, color: textColor, border: `1px solid ${gridColor}` }} />
              <Legend />
              <Area type="monotone" dataKey="CRITICAL" stackId="1" stroke="#ef4444" fill="#ef4444" fillOpacity={0.7} />
              <Area type="monotone" dataKey="HIGH" stackId="1" stroke="#f97316" fill="#f97316" fillOpacity={0.7} />
              <Area type="monotone" dataKey="MEDIUM" stackId="1" stroke="#eab308" fill="#eab308" fillOpacity={0.7} />
              <Area type="monotone" dataKey="LOW" stackId="1" stroke="#22c55e" fill="#22c55e" fillOpacity={0.5} />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Failure Risk Horizon */}
      <div className={`rounded-xl border p-5 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} shadow-sm`}>
        <h2 className="text-base font-semibold mb-4 dark:text-white">Failure-Risk Horizon — Top 15 Components</h2>
        {horizon.length === 0 ? (
          <div className="text-center text-gray-400 py-12">No prediction data — run pipeline first</div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={horizon} layout="vertical" margin={{ left: 160, right: 30, top: 5, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridColor} horizontal={false} />
              <XAxis type="number" domain={[0, 1]} tick={{ fill: textColor, fontSize: 11 }} tickFormatter={v => `${(v * 100).toFixed(0)}%`} />
              <YAxis type="category" dataKey="component_name" tick={{ fill: textColor, fontSize: 11 }} width={155} />
              <Tooltip
                contentStyle={{ background: bg, color: textColor, border: `1px solid ${gridColor}` }}
                formatter={(v: any, name: any, props: any) => [`${(Number(v) * 100).toFixed(1)}%  [${props.payload.risk_category}]`, 'Risk Score']}
              />
              <Bar dataKey="risk_score" radius={[0, 4, 4, 0]}>
                {horizon.map((entry) => (
                  <Cell key={entry.component_id} fill={RISK_COLORS[entry.risk_category] || '#94a3b8'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Fleet Health Matrix */}
      <div className={`rounded-xl border p-5 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'} shadow-sm`}>
        <h2 className="text-base font-semibold mb-4 dark:text-white">Fleet Health Matrix</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className={`border-b ${theme === 'dark' ? 'border-gray-700' : 'border-gray-200'}`}>
                <th className="text-left py-2 px-3 font-medium text-gray-500">Asset</th>
                <th className="text-left py-2 px-3 font-medium text-gray-500">Type</th>
                <th className="text-left py-2 px-3 font-medium text-gray-500">Readiness</th>
                <th className="text-left py-2 px-3 font-medium text-gray-500">Health Score</th>
                <th className="text-left py-2 px-3 font-medium text-gray-500">Components</th>
                <th className="text-left py-2 px-3 font-medium text-gray-500">Max Risk</th>
              </tr>
            </thead>
            <tbody>
              {matrixAssets.map((asset: any) => {
                const maxRisk = asset.components.reduce((m: number, c: any) => Math.max(m, c.risk_score ?? 0), 0);
                const maxCat = asset.components.find((c: any) => c.risk_score === maxRisk)?.risk_category ?? 'N/A';
                return (
                  <tr key={asset.asset_id} className={`border-b ${theme === 'dark' ? 'border-gray-700 hover:bg-gray-700' : 'border-gray-100 hover:bg-gray-50'} cursor-pointer`}
                    onClick={() => window.location.href = `/assets/${asset.asset_identifier}`}>
                    <td className="py-2 px-3 font-medium dark:text-white">{asset.asset_identifier}</td>
                    <td className="py-2 px-3 text-gray-500">{asset.asset_type}</td>
                    <td className="py-2 px-3">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium`} style={{ background: READINESS_COLORS[asset.readiness_status] + '20', color: READINESS_COLORS[asset.readiness_status] }}>
                        {asset.readiness_status ?? 'N/A'}
                      </span>
                    </td>
                    <td className="py-2 px-3">
                      {asset.health_score != null ? (
                        <div className="flex items-center gap-2">
                          <div className="w-20 h-2 bg-gray-200 dark:bg-gray-600 rounded-full overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${asset.health_score * 100}%`, background: asset.health_score > 0.7 ? '#22c55e' : asset.health_score > 0.4 ? '#eab308' : '#ef4444' }} />
                          </div>
                          <span className="text-xs text-gray-500">{(asset.health_score * 100).toFixed(0)}%</span>
                        </div>
                      ) : '—'}
                    </td>
                    <td className="py-2 px-3 text-gray-500">{asset.components?.length ?? 0}</td>
                    <td className="py-2 px-3">
                      <span className="text-xs font-medium" style={{ color: RISK_COLORS[maxCat] }}>
                        {(maxRisk * 100).toFixed(0)}% {maxCat}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

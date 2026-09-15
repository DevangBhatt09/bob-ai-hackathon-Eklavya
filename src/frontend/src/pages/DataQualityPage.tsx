import { useEffect, useState } from 'react';
import { getFleetDataQualitySummary, listDataQuality, listAssets, getAssetDataQuality } from '../services/api';
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip } from 'recharts';
import { useTheme } from '../hooks/useTheme';

const QUALITY_COLORS: Record<string, string> = { EXCELLENT: '#22c55e', GOOD: '#3b82f6', FAIR: '#eab308', POOR: '#f97316', INSUFFICIENT: '#94a3b8' };

export default function DataQualityPage() {
  const { theme } = useTheme();
  const [summary, setSummary] = useState<any>(null);
  const [reports, setReports] = useState<any[]>([]);
  const [assets, setAssets] = useState<any[]>([]);
  const [selectedAsset, setSelectedAsset] = useState('');
  const [assetMetrics, setAssetMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const bg = theme === 'dark' ? '#1f2937' : '#ffffff';
  const textColor = theme === 'dark' ? '#e5e7eb' : '#374151';

  useEffect(() => {
    Promise.all([getFleetDataQualitySummary(), listDataQuality({ limit: 20 }), listAssets({ limit: 55 })])
      .then(([s, r, a]) => { setSummary(s); setReports(r.items || []); setAssets(a.items || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedAsset) { setAssetMetrics(null); return; }
    getAssetDataQuality(selectedAsset).then(setAssetMetrics).catch(() => {});
  }, [selectedAsset]);

  const radarData = assetMetrics ? [
    { metric: 'Completeness', value: Math.round(assetMetrics.completeness * 100) },
    { metric: 'Validity', value: Math.round(assetMetrics.validity * 100) },
    { metric: 'Consistency', value: Math.round(assetMetrics.consistency * 100) },
    { metric: 'Timeliness', value: Math.round(assetMetrics.timeliness * 100) },
  ] : [];

  if (loading) return <div className="p-6 text-center text-gray-500">Loading data quality metrics...</div>;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold dark:text-white">Data Quality Monitor</h1>

      {/* Fleet Summary */}
      {summary && (
        <div className={`rounded-xl border p-5 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
          <h2 className="text-base font-semibold mb-3 dark:text-white">Fleet Data Quality Distribution</h2>
          <div className="flex flex-wrap gap-3">
            {Object.entries(summary.distribution || {}).map(([level, count]) => (
              <div key={level} className="text-center">
                <div className="text-2xl font-bold" style={{ color: QUALITY_COLORS[level] }}>{String(count)}</div>
                <div className="text-xs text-gray-500">{level}</div>
              </div>
            ))}
            {summary.average_overall_score != null && (
              <div className="text-center ml-4 pl-4 border-l border-gray-200 dark:border-gray-600">
                <div className="text-2xl font-bold dark:text-white">{(summary.average_overall_score * 100).toFixed(0)}%</div>
                <div className="text-xs text-gray-500">Avg Score</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Per-asset quality */}
      <div className={`rounded-xl border p-5 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold dark:text-white">Asset Data Quality Profile</h2>
          <select className={`text-sm px-2 py-1 rounded border ${theme === 'dark' ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300'}`}
            value={selectedAsset} onChange={e => setSelectedAsset(e.target.value)}>
            <option value="">Select an asset...</option>
            {assets.map(a => <option key={a.asset_id} value={a.asset_id}>{a.asset_id}</option>)}
          </select>
        </div>
        {assetMetrics ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <div className="flex items-center gap-2 mb-3">
                <span className="text-sm font-medium dark:text-white">Overall: </span>
                <span className="text-lg font-bold" style={{ color: QUALITY_COLORS[assetMetrics.quality_level] }}>{(assetMetrics.overall_score * 100).toFixed(0)}%</span>
                <span className="text-xs px-2 py-0.5 rounded" style={{ background: QUALITY_COLORS[assetMetrics.quality_level] + '20', color: QUALITY_COLORS[assetMetrics.quality_level] }}>{assetMetrics.quality_level}</span>
              </div>
              <div className="space-y-2 text-sm">
                {[
                  ['Completeness', assetMetrics.completeness],
                  ['Validity', assetMetrics.validity],
                  ['Consistency', assetMetrics.consistency],
                  ['Timeliness', assetMetrics.timeliness],
                ].map(([label, value]) => (
                  <div key={String(label)} className="flex items-center gap-3">
                    <span className="w-28 text-gray-500 text-xs">{String(label)}</span>
                    <div className="flex-1 h-2 bg-gray-200 dark:bg-gray-600 rounded-full">
                      <div className="h-full rounded-full" style={{ width: `${Number(value) * 100}%`, background: Number(value) > 0.7 ? '#22c55e' : Number(value) > 0.4 ? '#eab308' : '#ef4444' }} />
                    </div>
                    <span className="text-xs w-10 text-right dark:text-white">{(Number(value) * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>
            <ResponsiveContainer width="100%" height={200}>
              <RadarChart data={radarData}>
                <PolarGrid stroke={theme === 'dark' ? '#374151' : '#e5e7eb'} />
                <PolarAngleAxis dataKey="metric" tick={{ fill: textColor, fontSize: 11 }} />
                <PolarRadiusAxis domain={[0, 100]} tick={{ fill: textColor, fontSize: 10 }} />
                <Radar name="Quality" dataKey="value" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.3} />
                <Tooltip contentStyle={{ background: bg, color: textColor }} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        ) : <div className="text-center text-gray-400 py-12">Select an asset to view its data quality profile</div>}
      </div>
    </div>
  );
}

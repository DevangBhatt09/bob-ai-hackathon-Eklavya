import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listAssets } from '../services/api';
import { useTheme } from '../hooks/useTheme';

const TYPE_COLORS: Record<string, string> = {
  ROTARY_WING: '#6366f1',
  FIXED_WING: '#3b82f6',
  GROUND_VEHICLE: '#22c55e',
  MARITIME: '#06b6d4',
  SUPPORT_EQUIPMENT: '#94a3b8',
};

export default function AssetExplorerPage() {
  const { theme } = useTheme();
  const navigate = useNavigate();
  const [assets, setAssets] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');

  useEffect(() => {
    listAssets({ limit: 55 })
      .then(d => { setAssets(d.items || []); setTotal(d.total || 0); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const filtered = assets.filter(a =>
    (!filter || a.asset_id.toLowerCase().includes(filter.toLowerCase()) || a.name.toLowerCase().includes(filter.toLowerCase())) &&
    (!typeFilter || a.asset_type === typeFilter)
  );

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold dark:text-white">Asset Explorer</h1>
        <span className="text-sm text-gray-500">{total} assets total</span>
      </div>
      <div className="flex gap-3 flex-wrap">
        <input
          className={`px-3 py-2 rounded-lg border text-sm flex-1 min-w-48 ${theme === 'dark' ? 'bg-gray-700 border-gray-600 text-white placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
          placeholder="Search asset ID or name..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
        <select
          className={`px-3 py-2 rounded-lg border text-sm ${theme === 'dark' ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'}`}
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
        >
          <option value="">All Types</option>
          {['ROTARY_WING', 'FIXED_WING', 'GROUND_VEHICLE', 'MARITIME', 'SUPPORT_EQUIPMENT'].map(t => (
            <option key={t} value={t}>{t.replace(/_/g, ' ')}</option>
          ))}
        </select>
      </div>
      {loading ? (
        <div className="text-center py-16 text-gray-500">Loading assets...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map(asset => (
            <div
              key={asset.asset_id}
              onClick={() => navigate(`/assets/${asset.asset_id}`)}
              className={`rounded-xl border p-4 cursor-pointer transition-all hover:shadow-md ${theme === 'dark' ? 'bg-gray-800 border-gray-700 hover:border-gray-500' : 'bg-white border-gray-200 hover:border-gray-400'}`}
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="font-semibold text-sm dark:text-white">{asset.asset_id}</div>
                  <div className="text-xs text-gray-500">{asset.fleet || 'Unknown Fleet'}</div>
                </div>
                <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: (TYPE_COLORS[asset.asset_type] || '#94a3b8') + '20', color: TYPE_COLORS[asset.asset_type] || '#94a3b8' }}>
                  {asset.asset_type?.replace(/_/g, ' ')}
                </span>
              </div>
              <div className="text-xs text-gray-400 mt-2">
                <span>{asset.total_operating_hours?.toFixed(0)} hrs</span>
                {asset.location && <span className="ml-2">· {asset.location}</span>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

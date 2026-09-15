import { useState } from 'react';
import { uploadSensorCSV, uploadMaintenanceCSV, runPipelineSync } from '../services/api';
import { useTheme } from '../hooks/useTheme';

export default function IngestionPage() {
  const { theme } = useTheme();
  const [sensorFile, setSensorFile] = useState<File | null>(null);
  const [maintFile, setMaintFile] = useState<File | null>(null);
  const [sensorResult, setSensorResult] = useState<any>(null);
  const [maintResult, setMaintResult] = useState<any>(null);
  const [pipelineResult, setPipelineResult] = useState<any>(null);
  const [uploading, setUploading] = useState(false);
  const [pipelineRunning, setPipelineRunning] = useState(false);

  const handleSensorUpload = async () => {
    if (!sensorFile) return;
    setUploading(true);
    try {
      const result = await uploadSensorCSV(sensorFile);
      setSensorResult(result);
    } catch (e: any) {
      setSensorResult({ error: e.message });
    } finally { setUploading(false); }
  };

  const handleMaintUpload = async () => {
    if (!maintFile) return;
    setUploading(true);
    try {
      const result = await uploadMaintenanceCSV(maintFile);
      setMaintResult(result);
    } catch (e: any) {
      setMaintResult({ error: e.message });
    } finally { setUploading(false); }
  };

  const handleRunPipeline = async (limit: number) => {
    setPipelineRunning(true);
    try {
      const result = await runPipelineSync(undefined, limit);
      setPipelineResult(result);
    } catch (e: any) {
      setPipelineResult({ error: e.message });
    } finally { setPipelineRunning(false); }
  };

  const card = `rounded-xl border p-5 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`;
  const input = `px-3 py-2 rounded-lg border text-sm w-full ${theme === 'dark' ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'}`;

  return (
    <div className="p-6 space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold dark:text-white">Data Ingestion</h1>

      {/* Sensor CSV Upload */}
      <div className={card}>
        <h2 className="text-base font-semibold mb-3 dark:text-white">Upload Sensor CSV</h2>
        <p className="text-xs text-gray-500 mb-3">Required columns: timestamp, asset_id, sensor_type, sensor_value<br />Optional: component_id, unit, quality_flag</p>
        <div className="flex gap-2">
          <input type="file" accept=".csv" className={input} onChange={e => setSensorFile(e.target.files?.[0] || null)} />
          <button onClick={handleSensorUpload} disabled={!sensorFile || uploading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-50 hover:bg-blue-700 whitespace-nowrap">
            {uploading ? '...' : 'Upload'}
          </button>
        </div>
        {sensorResult && (
          <div className={`mt-3 p-3 rounded-lg text-sm ${sensorResult.error ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'} dark:bg-opacity-20`}>
            {sensorResult.error ? `Error: ${sensorResult.error}` : (
              <>Accepted: {sensorResult.valid_rows} rows · Rejected: {sensorResult.invalid_rows} · Persisted: {sensorResult.persisted}</>
            )}
          </div>
        )}
      </div>

      {/* Maintenance CSV Upload */}
      <div className={card}>
        <h2 className="text-base font-semibold mb-3 dark:text-white">Upload Maintenance CSV</h2>
        <p className="text-xs text-gray-500 mb-3">Required columns: maintenance_id, asset_id, maintenance_date, maintenance_type<br />Optional: component_id, description, technician, operating_hours, outcome</p>
        <div className="flex gap-2">
          <input type="file" accept=".csv" className={input} onChange={e => setMaintFile(e.target.files?.[0] || null)} />
          <button onClick={handleMaintUpload} disabled={!maintFile || uploading}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm disabled:opacity-50 hover:bg-blue-700 whitespace-nowrap">
            {uploading ? '...' : 'Upload'}
          </button>
        </div>
        {maintResult && (
          <div className={`mt-3 p-3 rounded-lg text-sm ${maintResult.error ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
            {maintResult.error ? `Error: ${maintResult.error}` : (
              <>Accepted: {maintResult.valid_rows} rows · Rejected: {maintResult.invalid_rows} · Persisted: {maintResult.persisted}</>
            )}
          </div>
        )}
      </div>

      {/* Analytics Pipeline Runner */}
      <div className={card}>
        <h2 className="text-base font-semibold mb-1 dark:text-white">Run Analytics Pipeline</h2>
        <p className="text-xs text-gray-500 mb-3">Runs anomaly detection, risk prediction, readiness assessment, and maintenance recommendations for all assets.</p>
        <div className="flex gap-2 flex-wrap">
          {[5, 10, 20].map(n => (
            <button key={n} onClick={() => handleRunPipeline(n)} disabled={pipelineRunning}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm disabled:opacity-50 hover:bg-indigo-700">
              {pipelineRunning ? 'Running...' : `Run on ${n} assets`}
            </button>
          ))}
        </div>
        {pipelineResult && (
          <div className={`mt-3 p-3 rounded-lg text-sm ${pipelineResult.error ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
            {pipelineResult.error ? `Error: ${pipelineResult.error}` : (
              <>
                <div className="font-medium">Pipeline complete — {pipelineResult.assets_processed} assets processed</div>
                <div className="mt-1 space-y-0.5">
                  {(pipelineResult.results || []).map((r: any, i: number) => (
                    <div key={i} className="text-xs">{r.asset_id}: {r.error || `anomalies=${r.anomalies_detected} risk=${r.overall_risk} readiness=${r.readiness_status}`}</div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

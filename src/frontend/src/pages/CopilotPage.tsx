import { useState, useRef, useEffect } from 'react';
import { copilotQuery, listAssets, getCopilotHealth } from '../services/api';
import { useTheme } from '../hooks/useTheme';

interface Message { role: 'user' | 'assistant'; content: string; timestamp: string; }

const DISCLAIMER = "AI-generated maintenance recommendations are decision-support outputs only. Final readiness and maintenance decisions require qualified human review.";

export default function CopilotPage() {
  const { theme } = useTheme();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [assetId, setAssetId] = useState('');
  const [assets, setAssets] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [geminiAvailable, setGeminiAvailable] = useState<boolean | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listAssets({ limit: 55 }).then(d => setAssets(d.items || [])).catch(() => {});
    getCopilotHealth().then(d => setGeminiAvailable(d.gemini_configured)).catch(() => {});
  }, []);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [messages]);

  const send = async () => {
    if (!input.trim()) return;
    const userMsg: Message = { role: 'user', content: input, timestamp: new Date().toISOString() };
    setMessages(prev => [...prev, userMsg]);
    const q = input;
    setInput('');
    setLoading(true);
    try {
      const res = await copilotQuery(q, assetId || undefined);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: res.response,
        timestamp: new Date().toISOString(),
      }]);
    } catch (e: any) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${e.message}`, timestamp: new Date().toISOString() }]);
    } finally {
      setLoading(false);
    }
  };

  const SUGGESTIONS = [
    "What are the highest risk components in the fleet right now?",
    "Which assets need immediate maintenance attention?",
    "Explain what a CRITICAL anomaly on the vibration sensor means.",
    "What maintenance actions should I prioritize this week?",
  ];

  return (
    <div className={`h-[calc(100vh-112px)] flex flex-col p-6 gap-4`}>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold dark:text-white">Maintenance Copilot</h1>
          <p className="text-sm text-gray-500 mt-0.5">AI-powered maintenance engineering assistant</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2 py-1 rounded-full ${geminiAvailable ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300' : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300'}`}>
            {geminiAvailable === null ? '...' : geminiAvailable ? 'Gemini Active' : 'Gemini Not Configured'}
          </span>
          <select
            className={`px-2 py-1 text-sm rounded-lg border ${theme === 'dark' ? 'bg-gray-700 border-gray-600 text-white' : 'bg-white border-gray-300 text-gray-900'}`}
            value={assetId}
            onChange={e => setAssetId(e.target.value)}
          >
            <option value="">All Assets</option>
            {assets.map(a => <option key={a.asset_id} value={a.asset_id}>{a.asset_id}</option>)}
          </select>
        </div>
      </div>

      {/* Chat area */}
      <div className={`flex-1 overflow-y-auto rounded-xl border p-4 space-y-4 ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-gray-50 border-gray-200'}`}>
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center gap-4 text-center">
            <div className="text-4xl">🔧</div>
            <div className="text-lg font-semibold dark:text-white">Ask the Maintenance Copilot</div>
            <p className="text-sm text-gray-500 max-w-md">Get AI-powered maintenance insights based on real sensor data, anomaly detection, and risk predictions.</p>
            <div className="flex flex-col gap-2 mt-2">
              {SUGGESTIONS.map(s => (
                <button key={s} onClick={() => setInput(s)}
                  className={`text-sm px-4 py-2 rounded-lg border text-left hover:border-blue-400 transition-colors ${theme === 'dark' ? 'border-gray-600 text-gray-300 hover:bg-gray-700' : 'border-gray-200 text-gray-600 hover:bg-white'}`}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm flex-shrink-0 ${m.role === 'user' ? 'bg-blue-600 text-white' : 'bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-200'}`}>
                {m.role === 'user' ? 'U' : '🤖'}
              </div>
              <div className={`rounded-xl px-4 py-3 max-w-2xl text-sm whitespace-pre-wrap ${m.role === 'user' ? 'bg-blue-600 text-white' : theme === 'dark' ? 'bg-gray-700 text-gray-100' : 'bg-white text-gray-800 border border-gray-200'}`}>
                {m.content}
              </div>
            </div>
          ))
        )}
        {loading && (
          <div className="flex gap-3">
            <div className="w-8 h-8 rounded-full bg-gray-300 dark:bg-gray-600 flex items-center justify-center text-sm">🤖</div>
            <div className={`rounded-xl px-4 py-3 text-sm ${theme === 'dark' ? 'bg-gray-700 text-gray-400' : 'bg-white text-gray-400 border border-gray-200'}`}>
              Analyzing maintenance data...
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Input */}
      <div className="flex gap-2">
        <input
          className={`flex-1 px-4 py-3 rounded-xl border text-sm ${theme === 'dark' ? 'bg-gray-800 border-gray-600 text-white placeholder-gray-400' : 'bg-white border-gray-300 text-gray-900'}`}
          placeholder="Ask about fleet maintenance, component health, anomalies..."
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }}}
        />
        <button onClick={send} disabled={loading || !input.trim()}
          className="px-5 py-3 bg-blue-600 text-white rounded-xl text-sm font-medium disabled:opacity-50 hover:bg-blue-700 transition-colors">
          Send
        </button>
      </div>

      <p className="text-xs text-gray-400 text-center">{DISCLAIMER}</p>
    </div>
  );
}

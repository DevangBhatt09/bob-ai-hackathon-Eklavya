import { BrowserRouter, Routes, Route, NavLink, useNavigate } from 'react-router-dom';
import { ThemeProvider, useTheme } from './hooks/useTheme';
import DashboardPage from './pages/DashboardPage';
import AssetExplorerPage from './pages/AssetExplorerPage';
import AssetDetailPage from './pages/AssetDetailPage';
import PredictiveMaintPage from './pages/PredictiveMaintPage';
import DataQualityPage from './pages/DataQualityPage';
import IngestionPage from './pages/IngestionPage';
import CopilotPage from './pages/CopilotPage';

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', exact: true },
  { to: '/assets', label: 'Asset Explorer' },
  { to: '/predictive', label: 'Predictive Maint.' },
  { to: '/data-quality', label: 'Data Quality' },
  { to: '/ingestion', label: 'Ingestion' },
  { to: '/copilot', label: 'Copilot' },
];

function Layout() {
  const { theme, toggle } = useTheme();

  return (
    <div className={`min-h-screen flex flex-col ${theme === 'dark' ? 'bg-gray-900 text-white' : 'bg-gray-50 text-gray-900'}`}>
      {/* Header */}
      <header className={`sticky top-0 z-50 flex items-center justify-between px-6 py-3 border-b shadow-sm ${theme === 'dark' ? 'bg-gray-800 border-gray-700' : 'bg-white border-gray-200'}`}>
        <div className="flex items-center gap-3">
          <span className="text-xl font-black tracking-tight text-blue-600">HUMS</span>
          <span className="text-sm font-medium text-gray-500 hidden sm:block">Mission Readiness Copilot</span>
        </div>
        <nav className="hidden md:flex items-center gap-1">
          {NAV_ITEMS.map(({ to, label, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-50 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={toggle}
          className={`p-2 rounded-lg text-sm border transition-colors ${theme === 'dark' ? 'border-gray-600 text-gray-300 hover:bg-gray-700' : 'border-gray-200 text-gray-600 hover:bg-gray-100'}`}
          title="Toggle theme"
        >
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>
      </header>

      {/* Main */}
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/assets" element={<AssetExplorerPage />} />
          <Route path="/assets/:assetId" element={<AssetDetailPage />} />
          <Route path="/predictive" element={<PredictiveMaintPage />} />
          <Route path="/data-quality" element={<DataQualityPage />} />
          <Route path="/ingestion" element={<IngestionPage />} />
          <Route path="/copilot" element={<CopilotPage />} />
        </Routes>
      </main>

      {/* Footer disclaimer */}
      <footer className={`text-center py-3 text-xs border-t ${theme === 'dark' ? 'bg-gray-800 border-gray-700 text-gray-500' : 'bg-white border-gray-200 text-gray-400'}`}>
        AI-generated maintenance recommendations are decision-support outputs only. Final readiness and maintenance decisions require qualified human review.
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Layout />
      </BrowserRouter>
    </ThemeProvider>
  );
}

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // ── Semantic status colors ────────────────────────────────────────────
        ready: {
          DEFAULT: '#16a34a',
          light: '#dcfce7',
          dark: '#14532d',
        },
        caution: {
          DEFAULT: '#d97706',
          light: '#fef3c7',
          dark: '#78350f',
        },
        maintenance: {
          DEFAULT: '#dc2626',
          light: '#fee2e2',
          dark: '#7f1d1d',
        },
        'not-ready': {
          DEFAULT: '#7c3aed',
          light: '#ede9fe',
          dark: '#3b0764',
        },
        // ── Risk levels ───────────────────────────────────────────────────────
        'risk-low': '#16a34a',
        'risk-medium': '#d97706',
        'risk-high': '#dc2626',
        'risk-critical': '#7c3aed',
        // ── Application surfaces (light mode) ─────────────────────────────────
        background: '#f8fafc',
        surface: '#ffffff',
        'surface-secondary': '#f1f5f9',
        border: '#e2e8f0',
        'text-primary': '#1e293b',
        'text-secondary': '#64748b',
        accent: '#0f172a',
        // ── Application surfaces (dark mode variables — applied via CSS) ──────
      },
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Consolas', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)',
        'card-hover': '0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.05)',
      },
    },
  },
  plugins: [],
}

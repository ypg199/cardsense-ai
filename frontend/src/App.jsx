import { BrowserRouter, Routes, Route } from 'react-router-dom'
import UploadPage from './pages/UploadPage.jsx'
import UtilizationPage from './pages/UtilizationPage.jsx'
import ResultsPage from './pages/ResultsPage.jsx'
import SpendAnalyserPage from './pages/SpendAnalyserPage.jsx'
import SpendUploadPage from './pages/SpendUploadPage.jsx'
import { NotFound } from './components/Brand.jsx'

const globalStyles = `
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --navy-950: #06091a;
    --navy-900: #0b1021;
    --navy-800: #111827;
    --navy-700: #1a2235;
    --navy-600: #253048;
    --navy-500: #334466;
    --slate-400: #94a3b8;
    --slate-300: #cbd5e1;
    --slate-200: #e2e8f0;
    --white: #f8fafc;

    --amber-500: #f59e0b;
    --amber-400: #fbbf24;
    --amber-300: #fcd34d;
    --green-500: #22c55e;
    --green-400: #4ade80;
    --red-500: #ef4444;
    --red-400: #f87171;
    --orange-500: #f97316;
    --orange-400: #fb923c;
    --blue-400: #60a5fa;

    --font-display: 'DM Serif Display', Georgia, serif;
    --font-sans: 'DM Sans', system-ui, sans-serif;
    --font-mono: 'DM Mono', 'Courier New', monospace;

    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 16px;
    --radius-xl: 24px;

    --on-accent: #06091a;       /* text on amber buttons */
    --tint: 255, 255, 255;      /* rgb for faint overlays: rgba(var(--tint), 0.03) */
    --overlay: rgba(6, 9, 26, 0.86);
    color-scheme: dark;

    --shadow-glow-amber: 0 0 20px rgba(245,158,11,0.15);
    --shadow-glow-green: 0 0 20px rgba(34,197,94,0.15);
    --transition: 220ms cubic-bezier(0.4, 0, 0.2, 1);
  }

  /* Light theme: the same tokens, re-stepped for a light surface. Follows the
     system setting unless the visitor picked a theme with the toggle. */
  :root[data-theme='light'] {
    --navy-950: #f5f6fa;
    --navy-900: #ffffff;
    --navy-800: #f0f2f7;
    --navy-700: #e4e8f0;
    --navy-600: #d3d9e4;
    --navy-500: #aab4c5;
    --slate-400: #5b6779;
    --slate-300: #3f4a5c;
    --slate-200: #283244;
    --white: #0f172a;

    --amber-500: #f59e0b;
    --amber-400: #b45309;
    --amber-300: #92400e;
    --green-500: #16a34a;
    --green-400: #15803d;
    --red-500: #dc2626;
    --red-400: #b91c1c;
    --orange-500: #ea580c;
    --orange-400: #c2410c;
    --blue-400: #1d4ed8;

    --tint: 15, 23, 42;
    --overlay: rgba(245, 246, 250, 0.9);
    --shadow-glow-amber: 0 0 20px rgba(245,158,11,0.12);
    --shadow-glow-green: 0 0 20px rgba(22,163,74,0.12);
    color-scheme: light;
  }
  @media (prefers-color-scheme: light) {
    :root:not([data-theme='dark']) {
    --navy-950: #f5f6fa;
    --navy-900: #ffffff;
    --navy-800: #f0f2f7;
    --navy-700: #e4e8f0;
    --navy-600: #d3d9e4;
    --navy-500: #aab4c5;
    --slate-400: #5b6779;
    --slate-300: #3f4a5c;
    --slate-200: #283244;
    --white: #0f172a;

    --amber-500: #f59e0b;
    --amber-400: #b45309;
    --amber-300: #92400e;
    --green-500: #16a34a;
    --green-400: #15803d;
    --red-500: #dc2626;
    --red-400: #b91c1c;
    --orange-500: #ea580c;
    --orange-400: #c2410c;
    --blue-400: #1d4ed8;

    --tint: 15, 23, 42;
    --overlay: rgba(245, 246, 250, 0.9);
    --shadow-glow-amber: 0 0 20px rgba(245,158,11,0.12);
    --shadow-glow-green: 0 0 20px rgba(22,163,74,0.12);
    color-scheme: light;
    }
  }

  html, body { height: 100%; }

  body {
    background: var(--navy-950);
    transition: background-color var(--transition), color var(--transition);
    color: var(--white);
    font-family: var(--font-sans);
    font-size: 15px;
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
    overflow-x: hidden;
  }

  /* Subtle grid texture overlay */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(var(--tint), 0.015) 1px, transparent 1px),
      linear-gradient(90deg, rgba(var(--tint), 0.015) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
    z-index: 0;
  }

  #root { position: relative; z-index: 1; min-height: 100vh; }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: var(--navy-900); }
  ::-webkit-scrollbar-thumb { background: var(--navy-600); border-radius: 3px; }

  /* Respect reduced-motion preferences across every page */
  @media (prefers-reduced-motion: reduce) {
    *:not(.fsl-ring):not([class*='spinner']), *::before, *::after {
      animation-duration: 1ms !important; transition-duration: 1ms !important;
    }
  }

  /* Shared utilities */
  .mono { font-family: var(--font-mono); }
  .amount {
    font-family: var(--font-mono);
    font-weight: 500;
    letter-spacing: -0.02em;
  }

  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(16px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes fadeIn {
    from { opacity: 0; }
    to   { opacity: 1; }
  }
  @keyframes shimmer {
    0%   { background-position: -200% center; }
    100% { background-position: 200% center; }
  }
  @keyframes pulse-ring {
    0%   { transform: scale(1);   opacity: 0.6; }
    100% { transform: scale(1.5); opacity: 0; }
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  @keyframes slideIn {
    from { opacity: 0; transform: translateX(24px); }
    to   { opacity: 1; transform: translateX(0); }
  }
`

export default function App() {
  return (
    <>
      <style>{globalStyles}</style>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/spend" element={<SpendUploadPage />} />
          <Route path="/quiz/:sessionId" element={<UtilizationPage />} />
          <Route path="/results/:sessionId" element={<ResultsPage />} />
          <Route path="/analyser/:sessionId" element={<SpendAnalyserPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </>
  )
}

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        /* Surfaces */
        page: '#F8FAFC',      // page/canvas background (slate-50)
        card: '#FFFFFF',      // card/panel/modal surface
        subtle: '#F1F5F9',    // secondary surface: table headers, code background, hover rows (slate-100)
        /* Text */
        ink: {
          DEFAULT: '#0F172A', // primary text (slate-900)
          soft: '#334155',    // secondary text (slate-700)
          muted: '#475569',   // helper text (slate-600)
          faint: '#64748B',   // placeholder/disabled helper (slate-500)
        },
        /* Borders */
        line: {
          DEFAULT: '#E2E8F0', // default border (slate-200)
          strong: '#CBD5E1',  // strong border/hover (slate-300)
          soft: '#F1F5F9',    // weak divider (= subtle)
        },
        /* Primary color (anchors: 800=#1E40AF, 500=#3B82F6) */
        blue: {
          50: '#EFF6FF',
          100: '#DBEAFE',
          200: '#BFDBFE',
          300: '#93C5FD',
          400: '#60A5FA',
          500: '#3B82F6',
          600: '#2563EB',
          700: '#1D4ED8',
          800: '#1E40AF',
          900: '#1E3A8A',
        },
        /* Semantic colors (DEFAULT=icons/white-on-solid text/solid background, soft=light background, deep=body text on soft background) */
        success: { DEFAULT: '#15803D', soft: '#F0FDF4', deep: '#166534' },
        warning: { DEFAULT: '#D97706', soft: '#FFFBEB', deep: '#B45309' },
        danger: { DEFAULT: '#DC2626', soft: '#FEF2F2', deep: '#B91C1C' },
        info: { DEFAULT: '#2563EB', soft: '#EFF6FF', deep: '#1E40AF' },
        /* AI feature color (indigo, distinct from the primary blue; use deep for text on the soft background) */
        ai: { DEFAULT: '#4F46E5', soft: '#EEF2FF', deep: '#3730A3' },
        /* Lineage edge source colors (used by getEdgeVisual for its four forms, SVG stroke) */
        lineage: {
          imported: '#475569',        // imported field-level (solid 1.55)
          'imported-weak': '#64748B', // imported table-level (dashed 1.4)
          manual: '#D97706',          // manually confirmed
          ai: '#4F46E5',              // AI suggested (dashed + animated)
          derived: '#94A3B8',         // view-derived: inferred link from same-name field matching across table-level lineage
          focus: '#DC2626',           // field trace highlight (= danger)
        },
      },
      fontFamily: {
        sans: ['"Noto Sans SC"', '"PingFang SC"', '"Microsoft YaHei"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', '"SFMono-Regular"', 'Menlo', 'Consolas', 'monospace'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(15, 23, 42, 0.05), 0 2px 8px -4px rgba(15, 23, 42, 0.08)',
        node: '0 1px 2px rgba(15, 23, 42, 0.06), 0 4px 12px -6px rgba(15, 23, 42, 0.10)',
        'node-active':
          '0 0 0 1.5px rgba(37, 99, 235, 0.55), 0 8px 24px -12px rgba(30, 64, 175, 0.35)',
        float: '0 2px 6px rgba(15, 23, 42, 0.06), 0 12px 32px -12px rgba(15, 23, 42, 0.18)',
        modal: '0 8px 24px rgba(15, 23, 42, 0.12), 0 24px 64px -16px rgba(15, 23, 42, 0.25)',
      },
      backgroundImage: {
        'dot-grid':
          'radial-gradient(circle, rgba(148, 163, 184, 0.35) 1px, transparent 1px)',
      },
      backgroundSize: {
        'grid-24': '24px 24px',
      },
      transitionTimingFunction: {
        'out-quint': 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
      opacity: {
        15: '0.15', 35: '0.35', 45: '0.45', 55: '0.55', 65: '0.65', 85: '0.85', 92: '0.92', 98: '0.98',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'modal-in': {
          '0%': { opacity: '0', transform: 'translateY(14px) scale(0.985)' },
          '100%': { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        'soft-pulse': {
          '0%, 100%': { opacity: '0.45' },
          '50%': { opacity: '0.85' },
        },
        'drawer-in': {
          '0%': { opacity: '0', transform: 'translateX(16px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 300ms cubic-bezier(0.22, 1, 0.36, 1) both',
        'fade-in': 'fade-in 200ms ease-out both',
        'modal-in': 'modal-in 250ms cubic-bezier(0.22, 1, 0.36, 1) both',
        'soft-pulse': 'soft-pulse 1.8s ease-in-out infinite',
        'drawer-in': 'drawer-in 200ms cubic-bezier(0.22, 1, 0.36, 1) both',
      },
    },
  },
  plugins: [],
};

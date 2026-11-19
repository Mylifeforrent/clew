/**
 * Color values for the four lineage edge forms (single source of truth for the 00 §2.4 lineage color group).
 *
 * colors.lineage in tailwind.config.cjs must stay in sync with the values here;
 * LineageEdge.getEdgeVisual and the DatasetSidebar legend both import this module,
 * preventing the same set of hex values from scattering and drifting.
 *
 * Clew redesign (2026-10): manual amber → teal (making room for brand orange),
 * focus trace highlight red → brand orange ("light the thread"); danger red is reserved
 * for deletion / validation failures.
 */
export const EDGE_COLORS = {
  /** source='ai' candidate edge */
  ai: '#4F46E5',
  /** source='manual' manual edge */
  manual: '#0D9488',
  /** imported field-level edge */
  imported: '#475569',
  /** imported table-level edge (one step weaker) */
  importedWeak: '#64748B',
  /** View-derived: inferred line from matching same-named fields on both ends of table-level lineage */
  derived: '#94A3B8',
  /** Upstream/downstream trace highlight after clicking a field (= brand orange brand-600) */
  focus: '#EA580C',
} as const;

/** hex → rgba: dimmed arrow markers cannot inherit the path's opacity, so alpha is applied separately. */
export function withAlpha(hex: string, alpha: number): string {
  const value = hex.replace('#', '');
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

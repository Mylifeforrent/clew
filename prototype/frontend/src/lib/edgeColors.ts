/**
 * Color values for the four lineage edge forms (single source of truth for the 00 §2.4 lineage color group).
 *
 * colors.lineage in tailwind.config.cjs must stay consistent with the values here;
 * LineageEdge.getEdgeVisual and the DatasetSidebar legend both reference this module,
 * avoiding color drift from the same hex values scattered across files.
 */
export const EDGE_COLORS = {
  /** source='ai' candidate edge */
  ai: '#4F46E5',
  /** source='manual' manual edge */
  manual: '#D97706',
  /** imported field-level edge */
  imported: '#475569',
  /** imported table-level edge (one step weaker) */
  importedWeak: '#64748B',
  /** View-derived: inferred link from same-name field matching across the two ends of a table-level lineage */
  derived: '#94A3B8',
  /** Upstream/downstream trace highlight after clicking a field (same value as the danger semantic color) */
  focus: '#DC2626',
} as const;

/** hex → rgba: dimmed arrow markers cannot inherit the path opacity, so alpha must be given separately. */
export function withAlpha(hex: string, alpha: number): string {
  const value = hex.replace('#', '');
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Frontend role visibility helpers (UI layer).
 *
 * Note: this only decides whether write-action entry points are shown; the real
 * permission check always lives in the backend.
 * viewer hides all write entry points; editor can edit / annotate / tag; admin can
 * additionally roll back and manage users.
 */
import type { TranslateFn } from '../i18n';

export type Role = 'viewer' | 'editor' | 'admin' | (string & {});

export function isEditor(role: string): boolean {
  return role === 'editor' || role === 'admin';
}

export function isAdmin(role: string): boolean {
  return role === 'admin';
}

export function roleLabel(role: string, t: TranslateFn): string {
  switch (role) {
    case 'admin':
      return t('common.admin');
    case 'editor':
      return t('common.editor');
    case 'viewer':
      return t('common.viewer');
    default:
      return role || t('common.roleUnknown');
  }
}

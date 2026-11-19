/**
 * Frontend role visibility helpers (UI layer).
 *
 * Note: this only decides whether write-operation entry points are shown; real
 * permission checks always live in the backend. viewer hides all write entry points;
 * editor can edit/annotate/tag; admin can additionally roll back and manage users.
 */
export type Role = 'viewer' | 'editor' | 'admin' | (string & {});

export function isEditor(role: string): boolean {
  return role === 'editor' || role === 'admin';
}

export function isAdmin(role: string): boolean {
  return role === 'admin';
}

export function roleLabel(role: string): string {
  switch (role) {
    case 'admin':
      return 'Admin';
    case 'editor':
      return 'Editor';
    case 'viewer':
      return 'Read-only';
    default:
      return role || 'Unknown role';
  }
}

# 05 · Versions and users

> Role: the workspace's "governance and audit" layer. Covers four forms: ① `VersionDrawer` version drawer (480px; sections: import batches / business tags + tagging form / diff between tags / admin rollback); ② `HistoryDrawer` change history drawer (360px; timeline of fields/edges, before→after snapshots); ③ `UserManagementModal` user management modal (md 560, admin only); ④ `ConfirmDialog` generic second confirmation (sm 400, shared by rollback and edge deletion; doc 03 finalizes its spec at the deletion entry). The first two share the same drawer skeleton as doc 04 (00 §7.7).
>
> Basis and sources:
> - `docs/04_hifi/00_design-overview-and-tokens.md` (single source for tokens, referenced as "00 §x.x"; drawer §7.7, modal §7.6, button §7.1, input §7.2, select §7.3, badge §7.4, empty state §7.9, loading §7.10, layering §6)
> - `docs/02_prototype/clew-lofi-prototype.html` versions and users screen (information-architecture baseline: version table + tagging + diff summary + user table; the per-row role select and RBAC matrix are not implemented, see §3.3 note)
> - `docs/03_dev/02_frontend-development.md` §6 (responsibilities of the three components), §8 (role permission UI representation), §9.1 (user management fidelity gap `[TBD-BIZ]`)
> - `docs/03_dev/05_api-reference.md` §12 (version tags/diff/rollback), §4.2–4 (import batches), §11 (change_log row snapshots), §2.3–4 (users)
> - Component source: `VersionDrawer.tsx`, `HistoryDrawer.tsx`, `UserManagementModal.tsx`, `ConfirmDialog.tsx`
>
> Scope constraint: visual and layout changes only; no functional logic changes (tag creation/rollback chain, diff calculation, change snapshot rendering, user creation validation all keep the status quo); no new dependencies, no new components; the low-fidelity per-row role editing and RBAC permission matrix are **not designed as interactive controls** (no backend API, `[TBD-BIZ]`, see §3.3).

---

## 1. Page role and entry points

| Component | Form / width | Entry | Exit |
|---|---|---|---|
| `VersionDrawer` | Drawer `w-[480px]` (00 §4.5 version tier) | TopBar "Versions" button (02 §3.1#6) | Esc / overlay / close (during pendingRollback, Esc and overlay do not close; existing) |
| `HistoryDrawer` | Drawer `w-[360px]` (00 §4.5 change history tier) | `DetailPanel` / `EdgeDetailPanel` "Change history" entry row (03 §3.2⑨) | Esc / overlay / close |
| `UserManagementModal` | Modal md `max-w-[560px]` (00 §7.6) | TopBar user menu "User management" (admin only) | Esc / overlay / close (does not close during submitting; existing) |
| `ConfirmDialog` | Modal sm `max-w-[400px]` (00 §7.6) | VersionDrawer rollback / EdgeDetailPanel edge deletion (03) | Cancel / Esc / overlay (all locked during busy; existing); auto-closes after confirm |

Role gating (existing logic; visuals only "do not render write entries"): tagging form `canWrite=isEditor`; rollback button `canRollback=isAdmin`; viewer shows a lock hint (§3.2).

## 2. Layout structure

### 2.1 VersionDrawer (480px, sectioned; matches the status quo with no Tabs introduced)

```
┌──────────────────────────────────────────────────────────────┐ Overlay z-40 bg-slate-900/25 · Panel z-[41]
│ ① Header h-12 px-4 border-b                                  │ [tag icon block] Versions │ [↻][✕]
├──────────────────────────────────────────────────────────────┤
│ ② Scroll body flex-1 bg-page px-4 py-4                       │
│   · Info bar (rollback only undoes the change log…)          │
│   · Rollback success notice (conditional, success)           │
│   ⓪ Section: import batches (row = version no./format/file/  │
│      time·actor/status badge)                                │
│   ⓟ Section: business tags (row = name/anchor/time·          │
│      actor/rollback button admin) + tagging form             │
│   ⓓ Section: diff between tags (from/to selects +            │
│      calculate button + summary pills + change list)         │
├──────────────────────────────────────────────────────────────┤
│ (ConfirmDialog overlays the drawer at z-50/51)               │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 HistoryDrawer (360px)

```
┌──────────────────────────────────────────────────────────────────┐
│ ① Header h-12: [history block] eyebrow "Change history · field"  │
│    + title (mono) │ [↻][✕]                                       │
├──────────────────────────────────────────────────────────────────┤
│ ② Scroll body bg-page px-4 py-4                                  │
│   · entityKey card + description (reverse order · 50 entries ·   │
│      annotations not written)                                    │
│   · Timeline ol (border-l left axis + op-                        │
│      colored nodes + entry cards: op badge/#id/time              │
│      → before→after / snapshot → actor)                          │
└──────────────────────────────────────────────────────────────────┘
```

### 2.3 UserManagementModal (md 560)

```
┌────────────────────────────────────────────────────────────────────┐ max-w-[560px] max-h-[85vh]
│ Header h-12: [users block] Admin features/User management │[↻][✕]  │
│ Body flex-1 bg-page px-4 py-4:                                     │
│   ① User list (row = avatar/username + current account/            │
│      display name/role badge)                                      │
│   ② Add-user form (2×2 grid + create button)                       │
│   ③ [TBD-BIZ] role-editing restriction notice bar                  │
└────────────────────────────────────────────────────────────────────┘
```

Region sizes: headers are always `h-12` (00 §7.6/§7.7); scroll body `px-4 py-4`; spacing between section titles and content `space-y-5` (VersionDrawer); no modal footer (UserManagementModal currently has a footer-less structure, with primary actions inside the form, preserved).

## 3. Per-region visual specs

### 3.1 VersionDrawer

**Header**: `flex h-12 shrink-0 items-center justify-between gap-3 border-b border-line-soft px-4` — left: icon block `flex h-8 w-8 items-center justify-center rounded-lg border border-blue-200 bg-blue-50 text-blue-700` (tag 16px) + `text-[14px] font-semibold text-ink` "Versions"; right: refresh / close ghost icon buttons (`h-8 w-8 rounded-lg text-ink-faint hover:bg-subtle hover:text-ink-soft` + shared ring, same spec as 04 §3.1). The original header description text moves into the first item of the scroll body.

**Info bar (first item of scroll body)**: `flex items-start gap-2 rounded-lg border border-line bg-card px-3 py-2.5 text-[12px] leading-5 text-ink-muted` (info icon 12px `text-ink-faint`) "Rollback only undoes the change log; annotations are append-only and unaffected by rollback." — a neutral info bar, not the info blue background (not an action warning; limits blue area).

**Rollback success notice (conditional)**: `flex items-start gap-2 rounded-lg border border-success/25 bg-success-soft px-3 py-2.5 text-[12px] leading-4 text-success-deep` (check 12px + existing `rollbackNotice` copy).

**Section title row**: `mb-2 flex items-center justify-between` — h3 `flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint` (layers/tag/diff icon 11px) + right counter `font-mono text-[11px] tabular-nums text-ink-faint`.

**⓪ Import batch row** (container `divide-y divide-line-soft overflow-hidden rounded-xl border border-line bg-card`, row `flex flex-wrap items-center gap-x-2.5 gap-y-1 px-3 py-2.5`):

| Element | Spec |
|---|---|
| Version number | `font-mono text-[13px] font-semibold tabular-nums text-ink` "v{version_no}" |
| Format chip | `rounded border border-line bg-page px-1.5 py-px font-mono text-[11px] uppercase text-ink-faint` (00 §7.5) |
| File name | `min-w-0 flex-1 truncate font-mono text-[11px] text-ink-faint` (full value preserved in `title`; empty shows "—") |
| Time · actor | `shrink-0 font-mono text-[11px] text-ink-faint` |
| Status badge | Active: `rounded-full border border-transparent bg-success-soft px-1.5 py-px font-mono text-[11px] text-success-deep`; rolled back: `border-line bg-subtle text-ink-muted` (see Pending additions #2 at the end) |

**ⓟ Business tag row** (same container; row `px-3 py-2.5`):

- Main row `flex flex-wrap items-center gap-x-2 gap-y-1`: tag name `font-mono text-[13px] font-semibold text-blue-800`; anchor chip `rounded border border-line bg-page px-1.5 py-px font-mono text-[11px] tabular-nums text-ink-faint` "change seq #120"; time · actor `font-mono text-[11px] text-ink-faint`; **rollback button** (canRollback, `ml-auto`): danger ghost sm — `inline-flex h-7 items-center gap-1 rounded-md border border-danger/25 bg-danger-soft px-2 text-[11px] font-medium text-danger-deep transition-colors duration-150 hover:border-danger/45` + shared ring (rollback 11px "Roll back to this tag").
- Description (optional): `mt-1 break-words text-[12px] leading-4 text-ink-muted`.
- Empty state: `rounded-xl border border-dashed border-line px-3 py-4 text-center text-[12px] text-ink-muted` "No business tags yet. Tags anchor the current change sequence number for version diff and rollback." (existing copy).

**Tagging form (canWrite)**: outer card `mt-2.5 rounded-xl border border-line bg-card p-3`; row `flex flex-wrap items-center gap-2` — tag name `input.field-input h-8 w-[150px] font-mono text-[12px]` (`sr-only` label "Version tag name" + existing placeholder), description `input.field-input h-8 min-w-[160px] flex-1 text-[13px]` (sr-only label), submit primary `h-8 px-2.5 text-[12px]` (plus 11px; busy "Creating…" + small white spinner; empty name disabled/neutralized); helper note `mt-1.5 font-mono text-[11px] text-ink-faint` "Editor role and above can create; duplicate names return 409."; error `mt-1.5 rounded-md border border-danger/25 bg-danger-soft px-2 py-1.5 text-[11px] leading-4 text-danger-deep` `role="alert"`. Viewer branch: `mt-2 flex items-center gap-1.5 text-[11px] text-ink-faint` (lock 11px + existing copy).

**ⓓ Diff between tags**:

- Precondition (tags < 2): dashed empty state "Create at least two tags before comparing net changes between tags." (same spec as the tag empty state).
- Control row: outer card `rounded-xl border border-line bg-card p-3`; `flex flex-wrap items-end gap-2` — two labels (00 §7.2: `mb-1.5 block text-[12px] font-medium text-ink-soft` "Start tag / End tag") + native select (00 §7.3: `.field-input h-8 min-w-[130px] font-mono text-[12px] pr-8` + chevron 14px); arrow between them `pb-2 text-ink-faint` (arrow-right 12px, `aria-hidden`); calculate button secondary `h-8 px-3 text-[12px]` (diff 11px; busy "Calculating…" + spinner + `cursor-wait`).
- Error bar: danger combination `text-[11px] leading-4`, `role="alert"`.
- Result block `mt-3 border-t border-line-soft pt-3`: summary row `flex flex-wrap items-center gap-1.5` — range `font-mono text-[12px] font-medium text-ink-soft` "{from} → {to}" + three count pills (`rounded-full border border-transparent px-2 py-px font-mono text-[11px] tabular-nums`):
  - `+N added` → `bg-success-soft text-success-deep`; `~N modified` → `bg-warning-soft text-warning-deep`; `−N deleted` → `bg-danger-soft text-danger-deep`.
- **Change list (single column)**: `mt-2 max-h-[240px] overflow-y-auto divide-y divide-line-soft overflow-hidden rounded-lg border border-line-soft`, row `flex items-start gap-2 bg-card px-2.5 py-1.5` — op badge (same three-color group as above, `rounded border border-transparent px-1.5 py-px font-mono text-[11px]` "added/modified/deleted"), entity type `shrink-0 text-[11px] text-ink-faint` (dataset/field/lineage edge), entity key `min-w-0 break-all font-mono text-[12px] text-ink-soft`. A single-column list suffices at 480px wide (two columns would need ≥720px, not adopted).
- Empty diff: `mt-2 text-[12px] text-ink-muted` "No net changes between the two tags."
- Footnote: `mt-2 flex items-center gap-1 text-[11px] text-ink-faint` (info 10px) "Diffs are merged by the entity natural key and count net changes; annotations do not participate in diff statistics." (existing copy).

### 3.2 HistoryDrawer

**Header**: skeleton same as VersionDrawer (icon block becomes history 16px; eyebrow `font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint` "Change history · dataset/field/lineage edge" + title `min-w-0 truncate font-mono text-[13px] font-semibold text-ink`). entityKey moves into the first card of the scroll body (the h-12 header cannot fit a third line).

**First card**: `rounded-lg border border-line bg-card px-3 py-2.5` — entity key `break-all font-mono text-[12px] leading-4 text-ink-soft`; description `mt-1.5 flex items-start gap-1.5 text-[11px] leading-4 text-ink-muted` (info 11px `text-ink-faint`) "The change log is shown in reverse chronological order (up to 50 entries). Imports and manual edits both leave traces; annotations are not written to the change log." (existing copy).

**Timeline**: `relative space-y-2.5 border-l border-line-soft pl-4`; node `absolute -left-[21px] top-3 h-2 w-2 rounded-full ring-2 ring-card`, fill follows op: added `bg-success` / updated `bg-warning` / deleted `bg-danger` (double-encoded with the op badge, see Pending additions #3 at the end).

**Entry card**: `rounded-xl border border-line-soft bg-card px-3 py-2.5`:

- meta row `flex flex-wrap items-center gap-x-2 gap-y-1`: op badge (same three-color group as §3.1 ⓓ); `#id` `font-mono text-[11px] tabular-nums text-ink-faint`; time `ml-auto font-mono text-[11px] text-ink-faint`.
- **updated (before→after)**: per-field rows `grid grid-cols-[64px_minmax(0,1fr)] gap-x-1.5 gap-y-1` — field name `text-[11px] leading-4 text-ink-faint` (`FIELD_LABELS`); value row `min-w-0 break-words font-mono text-[11px] leading-4`: before `line-through decoration-line-strong text-ink-faint` + arrow `mx-1 text-ink-faint` + after `text-blue-800` ("currently effective value" emphasis, same tier as the downstream endpoint emphasis in 03). No substantive change: "Content matches the previous version (no substantive change)." `text-[11px] leading-4 text-ink-faint`.
- **added / deleted (snapshot summary)**: `flex flex-wrap gap-x-3 gap-y-1`, each item `font-mono text-[11px] leading-4 text-ink-muted` (field-name prefix `text-ink-faint`), at most 5 items (current logic).
- Actor row: `mt-1.5 flex items-center gap-1 font-mono text-[11px] text-ink-faint` (user 10px "Actor {actor}").

### 3.3 UserManagementModal

**Overlay / panel**: 00 §7.6 — overlay `fixed inset-0 z-50 bg-slate-900/40 animate-fade-in` (clicking during submitting does not close; existing); panel `relative z-[51] mx-auto flex max-h-[85vh] w-full max-w-[560px] flex-col overflow-hidden rounded-xl border border-line bg-card shadow-modal animate-modal-in`.

**Header (h-12)**: left: icon block `flex h-8 w-8 items-center justify-center rounded-lg border border-blue-200 bg-blue-50 text-blue-700` (users 16px) + title group (eyebrow `font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint` "Admin features" + `text-[14px] font-semibold text-ink` "User management"); right: refresh / close (spec same as §3.1; close is the initial focus, existing). The original header description "Accounts are created by admin; the current API only supports adding users" moves into notice ③.

**Body**: `min-h-0 flex-1 overflow-y-auto bg-page px-4 py-4`.

**① User list**: section title row same as §3.1 (h3 "User list" + right `N accounts`). Container `divide-y divide-line-soft overflow-hidden rounded-xl border border-line bg-card`, row `flex items-center gap-2.5 px-3 py-2.5`:

| Element | Spec |
|---|---|
| Avatar | `flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-800 font-mono text-[11px] font-semibold text-white` (first 2 characters uppercased, same tier as the TopBar avatar, 02 §3.1#8) |
| Username | `truncate text-[13px] font-medium text-ink` |
| Current account badge | `rounded-full border border-blue-200 bg-blue-50 px-1.5 py-px font-mono text-[11px] text-blue-800` (only when `username === currentUsername`) |
| Display name | `mt-0.5 truncate font-mono text-[11px] text-ink-faint` (empty value "display name not registered" preserved) |
| Role badge | 00 §7.4 three role badges: admin `border-transparent bg-blue-800 text-white` / editor `border-blue-200 bg-blue-50 text-blue-800` / viewer `border-line bg-subtle text-ink-muted`; skeleton `inline-flex h-5 items-center rounded-full border px-2 text-[11px] font-medium leading-none` |

**[TBD-BIZ] UI note on the role-editing restriction**: the role column renders as a **read-only badge** (not a select control) — the backend has no role modification/deactivation API, and "whether an admin can change their own role / how to guarantee at least one admin" is undecided (dev doc §9.1, `[TBD-BIZ]`, to be confirmed by product at the stage when the backend adds admin APIs). The low-fidelity per-row role select and RBAC permission matrix are **not rendered**; reserved spec for a future opening: inline native select (00 §7.3, `h-7` compact tier) replaces the badge position, selected state uses the same color family as the badge, and a row changing one's own role gets a `border-warning/25` notice box — this reservation is visual indication only and is not part of this round's implementation.

**② Add-user form**: outer card `rounded-xl border border-line bg-card p-3` (section title "Add user" + user-plus 11px):

- Layout `grid gap-3 sm:grid-cols-2`; labels always 00 §7.2 (`mb-1.5 block text-[12px] font-medium text-ink-soft`, associated via `htmlFor`, replacing the existing `aria-label` wrapper approach).
- Username / initial password: `.field-input h-9 font-mono text-[13px]` (`autoComplete="off"` / `"new-password"` preserved); display name: `.field-input h-9 text-[13px]`; role: native select (00 §7.3: `.field-input h-9 pr-8` + chevron 14px, `ROLE_OPTIONS` three option labels preserved).
- Bottom row `mt-3 flex flex-wrap items-center gap-2`: create button primary `h-9 px-3 text-[13px]` (user-plus 12px; busy "Creating…" + small white spinner); helper note `font-mono text-[11px] text-ink-faint` "Passwords are stored only as salted hashes; duplicate usernames return 409.".
- `formError`: danger combination `rounded-md border border-danger/25 bg-danger-soft px-2.5 py-1.5 text-[12px] leading-4 text-danger-deep` `role="alert"` (client-side validation "username must be at least 2 characters / password must be at least 6 characters" and backend 409 copy both go here; existing logic).
- `notice`: success combination with the same skeleton `role="status"`.

**③ Role-editing restriction notice bar**: info combination `flex items-start gap-2 rounded-lg border border-blue-100 bg-blue-50 px-3 py-2.5 text-[12px] leading-5 text-blue-800` (info 12px) — copy follows the existing "Role changes and account deactivation are not yet available via API; the per-row role select and RBAC permission matrix in the prototype are not yet implemented; if adjustments are needed, please have the backend add admin APIs" + the header-migrated "Accounts are created by admin; the current API only supports adding users", suffixed with `[TBD-BIZ]` annotation semantics (the marker text does not appear visually; it persists as a notice bar).

### 3.4 ConfirmDialog (generic second confirmation, shared by rollback / edge deletion)

Finalized per 00 §7.6 sm tier (keeping the compact alertdialog form: icon block and title in the body area, no separate header bar):

- Overlay: `fixed inset-0 z-50 bg-slate-900/40 animate-fade-in` (clicking during busy does not close; existing; dangerous operations preserve this).
- Panel: `relative z-[51] mx-auto w-full max-w-[400px] overflow-hidden rounded-xl border border-line bg-card shadow-modal animate-modal-in`, `role="alertdialog" aria-modal="true"` (existing, preserved).
- Body: `px-4 py-4` — icon block `flex h-9 w-9 shrink-0 items-center justify-center rounded-lg`: danger `bg-danger-soft text-danger` (trash 17px) / non-danger `bg-warning-soft text-warning-deep` (warning 17px); title `text-[14px] font-semibold text-ink` (`aria-labelledby`); message `mt-1.5 text-[13px] leading-5 text-ink-muted`; mono note inside the rollback message `mt-1 font-mono text-[11px] leading-4 text-ink-faint` "Rollback can be executed repeatedly (idempotent); annotations will not be deleted." (existing copy).
- Footer: `flex h-12 items-center justify-end gap-2 border-t border-line-soft px-4` — cancel secondary `h-8 px-3 text-[13px]` (busy disabled `opacity-50`; initial focus, existing); confirm danger primary `h-8 px-3 text-[13px] font-medium text-white`: `bg-danger hover:bg-danger-deep active:bg-danger-deep disabled:opacity-70 disabled:cursor-wait` + shared ring (on solid backgrounds, per 00 §7.1 dark-background rule, change to `focus-visible:ring-white/60`), busy = spinner (`h-3 w-3 border-[1.5px] border-white/40 border-t-white`) + "Processing…".
- Rollback scenario copy (existing, preserved): title "Roll back to version tag"; message "Will undo all changes after tag '{name}' (including manual edits and import batches) and immediately refresh the canvas."; confirm button "Confirm rollback".

## 4. Component state specs

| Component | default | hover | active/focus | disabled/loading | selected |
|---|---|---|---|---|---|
| Drawer/modal header icon buttons | ghost `text-ink-faint` | `bg-subtle text-ink-soft` | shared ring (modal close is initial focus) | — | — |
| Batch/tag/user rows | static rows (not clickable) | — | — | — | — |
| Roll back to this tag | danger ghost sm `h-7` | `border-danger/45` | ring | during rollback execution, carried by ConfirmDialog busy | — |
| Tagging | primary `h-8` | `bg-blue-700` | `active:bg-blue-800` + ring | empty name / creating disabled neutralized + "Creating…" | — |
| diff start/end select | `.field-input h-8` (§7.3) | `border-line-strong` | blue focus (built-in) | disabled while calculating | — |
| Calculate diff | secondary `h-8` | `border-blue-400 text-blue-700` | ring | busy "Calculating…" `cursor-wait` | — |
| op badge / count pill / status badge | semantic group static | — | — | — | — |
| Timeline node | op color `ring-2 ring-card` | — | — | — | — |
| User form input / role select | `.field-input h-9` | `border-line-strong` | blue focus | submitting: entire group `opacity-50` | — |
| Create user | primary `h-9` | `bg-blue-700` | ring | busy "Creating…" + spinner | — |
| ConfirmDialog cancel | secondary `h-8` | secondary hover | ring; initial focus | busy disabled | — |
| ConfirmDialog confirm | `bg-danger text-white` | `bg-danger-deep` | `active:bg-danger-deep` + white ring | busy spinner "Processing…" | — |

## 5. Data states

| Region | Empty | Loading | Error |
|---|---|---|---|
| VersionDrawer main | batches empty dashed "No import batches yet"; tags empty dashed (§3.1) | 4 × `h-14 animate-soft-pulse rounded-xl border border-line bg-subtle` (00 §7.10 skeleton) | danger card `rounded-xl border border-danger/25 bg-danger-soft px-3.5 py-3` + body `text-[13px] leading-5 text-danger-deep` + "Reload" secondary sm `h-7` (refresh 11px), `role="alert"` |
| Tagging form | — | "Creating…" + spinner | `createError` danger bar `role="alert"` (including the 409 duplicate-name copy) |
| Tag diff | tags<2 dashed; empty diff "No net changes" | "Calculating…" + spinner | `diffError` danger bar (including backend copy for 404 tag not found / 400 start later than end) |
| Rollback | — | ConfirmDialog busy "Processing…" (Esc/overlay/cancel all locked, existing) | rollback failure goes to Toast error (existing `onNotify`, 00 §7.8); success = in-drawer success notice + Toast success + list refresh |
| HistoryDrawer | dashed "No change records yet" + description "Creation and modification of this entity have not yet been written to the change log." | 3 × `h-[86px] animate-soft-pulse rounded-xl border border-line bg-subtle` | danger card + reload (same spec as VersionDrawer) |
| UserManagementModal user list | — (the current admin always exists; no empty state) | 3 × `h-11 animate-soft-pulse …bg-subtle` | danger card (retry goes through the header refresh button, existing) |
| Add-user form | empty form | "Creating…" + spinner + entire group disabled | `formError` danger `role="alert"`; success `notice` success `role="status"` + form cleared and list refreshed (existing) |

## 6. Interaction and motion (00 §5)

| Interaction | Motion |
|---|---|
| Drawer slide-in (Version/History) | 200ms `out-quint` translateX (00 §7.7; `drawer-in` keyframe pending write-back, see Pending additions #1) |
| Modal entrance (UserModal / ConfirmDialog) | `animate-modal-in` 250ms `out-quint` (00 §5.2) |
| Overlay fade-in | `animate-fade-in` 200ms |
| Skeleton | `animate-soft-pulse` 1.8s (one of only two continuous animations; static under reduced-motion) |
| Button / select hover, rollback button hover | `transition-colors duration-150` |
| diff result block appearance | `animate-fade-in` 200ms (result is state feedback) |
| List items / timeline | no entrance animation (verification scenarios avoid flicker, per 03 §6 convention) |
| All | globally disabled under `prefers-reduced-motion` |

## 7. Change list for existing components

Same-name value swaps (pine→blue, rosewood/ember→danger, ochre→warning, ink/line same-name swaps) are handled by the global replacement in 00 §9; the table below lists only changes beyond that mapping.

| # | Component - current - target - tokens/classes involved |
|---|---|
| 1 | `VersionDrawer.tsx` - overlay `z-[70] bg-ink/40 backdrop-blur-[2px]`, panel `max-w-[620px] bg-surface animate-fade-in` - change overlay to `z-40 bg-slate-900/25` (blur removed), panel to `sm:w-[480px] bg-card` + slide-in - 00 §6/§7.7, `w-[480px]` |
| 2 | Same - header `py-3.5` three rows (22px display title + 9.5px description) - h-12 single row (icon block + `text-[14px]` title + refresh/close); description moves into the first info card of the body - `h-12`, `text-[14px]` |
| 3 | Same - scroll body `bg-[#fbf9f3]`, skeleton `bg-surface`, error card rosewood + retry button pine hover - `bg-page`, skeleton `bg-subtle`, error card danger group + secondary sm retry - `bg-page`, danger group |
| 4 | Same - rollback success notice `border-pine-200 bg-pine-50 text-pine-800 text-[10px]` - success combination `text-[12px] text-success-deep` - success group |
| 5 | Same - section title/counter `text-[8.5px]/[8px]` - both `text-[11px] tabular-nums` - font-size tiering |
| 6 | Same - batch row version no. `text-[10.5px]`, format/file/time `text-[8~8.5px]`, active badge `bg-pine-50 text-pine-700`, rolled back `bg-rosewood-soft text-rosewood-deep` - §3.1 table: version no. `text-[13px]`, the rest `text-[11px]`; active success group; rolled back changed to neutral `border-line bg-subtle text-ink-muted` (non-error semantics, see Pending additions #2) - `text-[13px]/[11px]`, success group, neutral badge |
| 7 | Same - tag name `text-pine-800 text-[10.5px]`, anchor chip 8px, rollback button `border-rosewood/20 hover:border-rosewood/40 ring-rosewood/30 text-[9px]` - tag name `text-blue-800 text-[13px]`, chip 11px, rollback button danger ghost sm + shared ring (§3.1) - `blue-800`, danger ghost sm |
| 8 | Same - tagging form card `bg-surface/70`, inputs `text-[10px]`, submit button `bg-pine-800 rounded-md disabled:opacity-50`, helper 8px, error bar rosewood 9px - card `bg-card`, inputs `.field-input h-8 text-[12px]/[13px]` + sr-only label, submit primary `h-8` + disabled neutralized, helper/error `text-[11px]` danger group - `bg-card`, `text-[11px]/[12px]` |
| 9 | Same - viewer hint `text-[8.5px]` - `text-[11px]` (lock 11px) - font-size tiering |
| 10 | Same - diff select `rounded-lg bg-surface focus:border-pine-500 text-[10px]`, label `text-[8px]`, calculate button `hover:border-pine-300 text-[9.5px]`, summary pill pine/ochre/rosewood `text-[8px]`, list row `bg-canvas/35 text-[8~8.5px]`, empty diff/footnote 8–9px - §3.1 ⓓ: select §7.3 `h-8 text-[12px]`, label §7.2 12px, calculate button secondary h-8 `text-[12px]`, pill three-color semantic group `text-[11px] tabular-nums`, list row `bg-card text-[12px]/[11px]`, empty diff `text-[12px] text-ink-muted`, footnote 11px - §7.2/§7.3, success/warning/danger groups, font-size tiering |
| 11 | `HistoryDrawer.tsx` - overlay `z-[75] bg-ink/40 blur`, panel `max-w-[520px] bg-surface` - overlay `z-40 bg-slate-900/25`, panel `sm:w-[360px] bg-card` + slide-in - 00 §7.7, `w-[360px]` |
| 12 | Same - header three rows (eyebrow 8.5px + title mono 12.5px + entityKey 8.5px) - h-12 single row (icon block + eyebrow 11px + title mono `text-[13px]`), entityKey moves into the first body card - `h-12`, `text-[13px]/[11px]` |
| 13 | Same - info card `border-line-soft bg-surface text-[9px]`, skeleton/error card surface/rosewood - info merged into first card `bg-card text-[11px] text-ink-muted`; skeleton `bg-subtle`; error danger group + secondary sm retry - `bg-card`, danger group |
| 14 | Same - timeline node `border-surface bg-pine-500` (always green), op badge pine/ochre/rosewood `text-[8px]`, entry card `bg-surface/85`, before/after `text-[8.5~9px]` after `text-pine-800`, snapshot 8.5px, actor 8px - nodes colored by op (success/warning/danger + `ring-2 ring-card`); badges three-color semantic group 11px; card `bg-card`; values `text-[11px]`, after `text-blue-800`; actor 11px - op colors, `text-[11px]`, `blue-800` |
| 15 | Same - empty state `text-[10px]/[9px]` - `text-[12px]/[11px]` - font-size tiering |
| 16 | `UserManagementModal.tsx` - overlay `z-[80] bg-ink/45 blur`, panel `max-w-[620px] rounded-2xl shadow-float max-h-[92vh]` - overlay `z-50 bg-slate-900/40` (blur removed), panel `max-w-[560px] rounded-xl shadow-modal max-h-[85vh]` - 00 §7.6 md tier |
| 17 | Same - header `py-3.5` two rows + icon block `border-pine-200 bg-pine-50 text-pine-700` + description 9.5px - h-12 single row (icon block blue family + eyebrow + `text-[14px]` title); description merged into notice ③ - `h-12`, `blue-200/50/700` |
| 18 | Same - avatar `bg-pine-800 text-[9px]`, username `text-[11px]`, current account badge `text-[7.5px]`, display name 8.5px, role chip `border-line bg-canvas/55 text-ink-muted font-mono` - avatar `bg-blue-800 text-[11px]`, username `text-[13px]`, badge `text-[11px]` blue family, display name 11px; **role chip replaced with the three role badges from 00 §7.4** (read-only, [TBD-BIZ] note in §3.3) - `bg-blue-800`, three role badges |
| 19 | Same - form label `text-[10px]` wrapper approach, input `text-[10.5px]`, select self-styled `rounded-xl bg-canvas/25 focus:pine`, create button `bg-pine-800 font-semibold text-[10px] disabled:opacity-65`, helper 8px, error/success bars 9.5px rosewood/pine - label §7.2 12px + `htmlFor`; inputs `.field-input h-9 text-[13px]` (username/password `font-mono`); select §7.3; create primary `h-9` + disabled neutralized; helper `text-[11px]`; error danger / success success groups `text-[12px]` - §7.2/§7.3, `h-9`, danger/success groups |
| 20 | Same - bottom hint `text-[8.5px] text-ink-faint` - info combination notice bar (§3.3 ③) `text-[12px] text-blue-800` - info group |
| 21 | `ConfirmDialog.tsx` - overlay `z-[90] bg-ink/45 blur`, panel `max-w-[400px] rounded-2xl shadow-float` - overlay `z-50 bg-slate-900/40` (blur removed), panel `rounded-xl shadow-modal` (width 400 is already the sm tier) - 00 §7.6 sm tier |
| 22 | Same - icon block `bg-rosewood-soft` / `bg-ochre-soft rounded-xl`, title `text-[13px]`, message `text-[10.5px]`, footer `py-3 bg-canvas/45` buttons self-styled `text-[10.5px] font-semibold bg-rosewood/pine-800 hover:-deep` - icon block danger/warning groups `rounded-lg`; message `text-[13px] leading-5`; footer h-12 structure + cancel secondary / confirm danger primary `h-8 text-[13px] font-medium` + shared ring (§3.4) - danger/warning groups, `h-12`, `h-8` |

## 8. Accessibility notes (specific to this page)

1. **Dual channel for destructive operations**: rollback must go through ConfirmDialog (`role="alertdialog"`) + text explanation "will undo … all changes"; danger is not conveyed by red alone (icon + complete sentence).
2. **busy locking**: during ConfirmDialog / UserModal submitting, Esc, overlay click, and the cancel button are all disabled (existing behavior preserved item by item); during VersionDrawer pendingRollback, Esc and the overlay do not close the drawer (existing).
3. **Initial focus**: modals and drawers focus the close/cancel button on open (existing); restoring focus after close relies on the trigger button's DOM order (existing, no extra handling).
4. **Form labels**: inline inputs in the tagging row use `sr-only` labels (space-constrained scenario, allowed by 00 §7.2); all UserModal form fields change to visible labels + `htmlFor` (§7#19).
5. **Table/list semantics**: batches, tags, users, and diff lists are all semantic lists (`div` sections + counts announced by section titles); the timeline uses `ol` (existing, preserved).
6. **Color is not the only encoding**: op = color + text badge (added/modified/deleted); batch status = background + text (active/rolled back); timeline node colors are only redundant with the badge.
7. **Contrast spot checks**: `success-deep` on `success-soft` (6.81), `warning-deep` on `warning-soft` (4.84), `danger-deep` on `danger-soft` (5.91), `blue-800` on `card` (8.72), `white` on `bg-danger` (4.83) — all within the 00 §2.6 table.
8. **Roles distinguishable**: the three role badges have text (admin/editor/viewer) and do not rely on color differences (viewer neutral gray remains readable).

## Pending tokens (suggested write-back to 00)

| # | Gap | Suggested value | Note |
|---|---|---|---|
| 1 | Drawer slide-in keyframe | `drawer-in` (200ms `out-quint` translateX) | Same item as 04 Pending additions #1; VersionDrawer / HistoryDrawer depend on the same |
| 2 | "Rolled back / invalidated" status badge scenario | neutral `border-line bg-subtle text-ink-muted` | The 00 §7.4 status badge table only has success/failure/in-progress/pending confirmation; a rolled-back batch is not error semantics, and mechanically mapping rosewood→danger would overstate it; suggest adding an "invalidated/rolled back" row |
| 3 | Timeline component spec | left axis `border-l border-line-soft pl-4` + node `h-2 w-2 rounded-full ring-2 ring-card` colored by semantics | 00 has no timeline spec; HistoryDrawer is the first consumer; suggest adding in §7 |
| 4 | diff count pill scenario | `+N / ~N / −N` reusing the success/warning/danger three groups + `tabular-nums` | 00 §7.4 does not list a "diff count" scenario row; this page and 06 (import report statistics) are the same pattern; suggest registering together |
| 5 | Inline compact form label convention | tagging row uses `sr-only` labels; modal forms use visible labels | 00 §7.2 defines only one tier of visible labels; suggest adding the convention allowing sr-only for "inline compact forms" |

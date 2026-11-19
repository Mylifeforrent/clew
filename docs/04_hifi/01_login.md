# 01 · Login Page

> Positioning: Clew's entry screen. Rendered by `App` when there is no valid session (first visit, or logout after an expired-JWT 401); after a successful login it calls `persistSession` and enters `Workspace` (document 02). It is the user's first impression of the product's character, and the only page where a large area of brand deep orange (`brand-900`) is allowed - inside the workbench, brand orange retreats to interaction semantics (00 §1.2 principle 3).
>
> Sources and references:
> - `docs/04_hifi/00_design-overview-and-tokens.md` (the sole source of every token in this document; references use the form "00 §x.x")
> - `docs/02_prototype/clew-lofi-prototype.html` login screen (centered-card baseline - this page finalizes it as a two-column split per the 00 decisions, see §2)
> - `docs/03_dev/02_frontend-development.md` §4 authentication (global 401 handling) and §6 component inventory (LoginPage responsibilities)
> - `prototype/frontend/src/components/LoginPage.tsx`, `Brand.tsx` (basis for the current state and the rework)
>
> Scope constraint: visual and layout changes only; login logic is unchanged (form validation, AbortController, and error branches all stay as they are); no new dependencies and no new components.

---

## 1. Page Positioning and Entry

| Item | Description |
|---|---|
| When it is shown | Rendered by `App` when no session is detected; session expiry is handled globally by the 401 handler, which logs out and returns to this page with a `notice` (a "login expired" style message) |
| Related components | `LoginPage.tsx` (including the internal illustration component `MiniNode`), `Brand.tsx` (`BrandMark` / `Brand`) |
| When it exits | On successful login it calls `onLoggedIn`, and `App` switches to `Workspace` (`key={token}`) |
| Page responsibilities | Brand presentation (left column) + authentication form (right column) + session-expiry notice (`notice`) + error feedback + submit loading state |

## 2. Layout Structure

**Finalized approach: large two-column split card** (not the low-fidelity centered card). Rationale: 00 already contains two decisions that presuppose a left column - the blue-900 usage "dark panel background on the left of the login page" (00 §2.1) and the 28px type-size exception "only in the left-column headline of the login page" (00 §3.2); and the existing implementation is already two-column, so the layout change is minimal. The left column carries the brand and product illustration, the right column carries the form, with clear separation of responsibilities.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Page  bg-page  p-3 sm:p-6 lg:p-8  min-h-dvh  flex items-center           │
│ ┌──────────────────────────────────────────────────────────────────────┐ │
│ │ Card  lg:min-h-[690px]  max-w-[1180px]  rounded-2xl                  │ │
│ │       border border-line  bg-card  shadow-float                      │ │
│ │       grid lg:grid-cols-[1.08fr_0.92fr] (2 cols >=lg, 1 below)       │ │
│ │ ┌────────────────────────────────┬─────────────────────────────────┐ │ │
│ │ │ Left column (brand panel)      │ Right column (form panel)       │ │ │
│ │ │ bg-blue-900                    │ bg-card                         │ │ │
│ │ │ px-10 py-9 xl:px-14 xl:py-11   │ px-6 py-10 sm:px-12 lg:px-14    │ │ │
│ │ │                                │ Content max-w-[372px] centered  │ │ │
│ │ │ (1) Top brand row  h-40        │ (1) eyebrow + title + note      │ │ │
│ │ │ (2) Headline (28px)            │ (2) notice bar (optional)       │ │ │
│ │ │ (3) Lineage MiniNode x3 + SVG  │ (3) Form fields + submit        │ │ │
│ │ │ (4) 3 features grid  border-t  │ (4) Security note + role chips  │ │ │
│ │ └────────────────────────────────┴─────────────────────────────────┘ │ │
│ └──────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

Area dimensions (all reuse or reference 00 tokens; `max-w-[1180px]`, `min-h-[690px]`, and the two-column ratio `1.08fr/0.92fr` are one-off layout values for this page, kept as they are):

| Area | Size / spacing |
|---|---|
| Page margin | `p-3 sm:p-6 lg:p-8` (00 §4.1 page-level spacing step) |
| Card | `max-w-[1180px]`, `lg:min-h-[690px]`, `rounded-2xl` (00 §4.2 dedicated 16px step for the login card), `shadow-float` (00 §4.4), `border border-line` |
| Left column padding | `px-10 py-9 xl:px-14 xl:py-11` (40/36 -> 56/44, page-level step) |
| Right column padding | `px-6 py-10 sm:px-12 lg:px-14`; form column `max-w-[372px]` centered |
| Block spacing | `space-y-4` between form fields (16px); major blocks inside the card at the `mt-8` level (00 §4.1) |
| Controls | Inputs `h-9` (36px, 00 §4.5 default form step); submit button `h-9` (lg step, 00 §4.5 "login submit" explicit 36px) |

## 3. Area-by-Area Visual Specs

### 3.1 Page Background and Card

- Page: `bg-page` (00 §2.2). **Remove** the existing `bg-fine-grid bg-grid-28` grid overlay and the `bg-pine-200/30 blur-3xl` glow orb on the left (00 §1.2 principle 1: no decorative halos; 00 §9.2 mapping table likewise).
- Card container:

```html
class="relative grid w-full max-w-[1180px] overflow-hidden rounded-2xl border border-line bg-card shadow-float lg:min-h-[690px] lg:grid-cols-[1.08fr_0.92fr]"
```

### 3.2 Left Column (Brand Panel, `bg-blue-900`)

Base color `bg-blue-900` (explicit decision in 00 §2.1). **Remove** all three decorative layers inside the left column (white 34px grid-line overlay, top-right `pine-500/30 blur-[90px]` glow orb, bottom-left `ember/20 blur-[110px]` glow orb) - the deep blue background plus the content hierarchy is enough on its own, 00 §1.2 principle 1. The left column is display-only (except the `aria-hidden` illustration), `hidden lg:flex` (hidden on narrow screens, kept as is).

Three tiers of text on the dark background (combination rules in "Tokens to Be Added" at the end; all color values come from the 00 blue scale): heading `text-white`, body `text-blue-100`, secondary/eyebrow `text-blue-300`.

**① Top brand row**

```html
<div class="flex items-center justify-between">
  <div class="flex items-center gap-2.5">
    <BrandMark size={34} className="text-blue-600" />   <!-- On the dark background the mark's base block uses blue-600 (a blue-800 block over blue-900 is only about 1.2:1, so the block almost disappears; blue-600 is the same step as the primary button and stays legible); dots/lines come from the Brand rework -->
    <div>
      <div class="font-sans text-[20px] font-semibold tracking-tight text-white">
        Lineage<span class="text-blue-300">Lite</span>
      </div>
      <div class="font-mono text-[11px] uppercase tracking-[0.2em] text-blue-300">Make data origins clearly visible</div>
    </div>
  </div>
  <span class="rounded-full border border-blue-700 px-3 py-1 font-mono text-[11px] uppercase tracking-[0.16em] text-blue-200">M3 · Editing and versioning</span>
</div>
```

(The version chip is information, not decoration, so it stays; its border uses `border-blue-700` instead of the out-of-scale `white/15`.)

**② Headline area**

- Eyebrow: `h-px w-8 bg-blue-400` short rule + `font-mono text-[11px] uppercase tracking-[0.2em] text-blue-300`, with the text "Field-level lineage · source files traceable".
- Headline (28px exception step, the only 700-weight large heading on the site, 00 §3.2 / §3.3):

```html
<h1 class="text-[28px] font-bold leading-[1.25] tracking-tight text-white">
  Every lineage trace,<br />lands back in its source file.
</h1>
```

- Subcopy: `mt-5 max-w-[430px] text-[13px] leading-6 text-blue-100`.

**③ Lineage illustration area (MiniNode x 3 + SVG connectors + bottom info bar)**

MiniNode is a product illustration in the spirit of "data ink" (not decoration); it stays, but is respecified for the dark background throughout:

| Element | Spec |
|---|---|
| Illustration card (idle) | `rounded-xl border border-blue-700 bg-blue-800`, header `h-9 border-b border-blue-700 bg-blue-800` (same layer as the body, separated by the border) |
| Illustration card (active/seed) | `rounded-xl border border-blue-300 bg-blue-800`; header `bg-blue-700`; status dot `h-1.5 w-1.5 rounded-full bg-blue-300` (idle cards use `bg-blue-500`) |
| Card title | `font-mono text-[11px] font-medium text-blue-100` (active card `text-white`) |
| Field row | `h-7 flex items-center justify-between px-3 font-mono text-[11px] text-blue-200`; active row (first row) `bg-blue-700/60 text-white` |
| Collapsed card body | `px-3 py-2.5 font-mono text-[11px] text-blue-300` |
| SVG connectors | imported line `stroke="#93C5FD"` (blue-300) at 1.2px; table-level dashed line `stroke-dasharray="4 4"`; AI suggestion dashed line `stroke="#EEF2FF"` (ai-soft, an indigo that is legible on the dark background) `strokeDasharray="5 4"`; node dots `fill="#BFDBFE"` (blue-200) / AI dot `fill="#EEF2FF"` |
| Bottom info bar | `rounded-lg border border-blue-700 bg-blue-800/85 px-3 py-2`; icon block `h-6 w-6 rounded-md bg-blue-700/60 text-blue-200`; file name `font-mono text-[11px] text-blue-100`; locator `font-mono text-[11px] text-blue-300` |

**④ Bottom three-feature grid**

`mt-8 grid grid-cols-3 gap-3 border-t border-blue-700 pt-5`; each cell: number `font-mono text-[11px] text-blue-300`, title `text-[12px] font-medium text-white`, description `font-mono text-[11px] text-blue-300`.

### 3.3 Right Column (Form Panel, `bg-card`)

**① Title group**

- Eyebrow: `h-px w-7 bg-blue-600` + `font-mono text-[11px] uppercase tracking-[0.18em] text-blue-700`, with the text "Workbench access".
- Title: `text-2xl font-semibold tracking-tight text-ink` (24px step, 00 §3.2 "login page main title"; replaces the existing 36px `font-display`).
- Description: `mt-2.5 text-[13px] leading-6 text-ink-muted`.
- Narrow-screen brand row (`lg:hidden`): `Brand compact` + `font-mono text-[11px] uppercase text-ink-faint`, keeping the current structure.

**② notice bar (session expiry, etc., optional)**

warning semantics (00 §2.3 explicit scenario "login expiry notice"):

```html
<div class="mb-5 flex gap-2.5 rounded-lg border border-warning/25 bg-warning-soft px-3.5 py-3 text-[13px] leading-5 text-warning-deep" role="status">
  <Icon name="info" size={14} className="mt-0.5 shrink-0" />
  <span>{notice}</span>
</div>
```

**③ Form**

Labels follow 00 §7.2 uniformly: `mb-1.5 block text-[12px] font-medium text-ink-soft`.

Username input (left icon spec 00 §7.2: icon `absolute left-3 text-ink-faint`, `focus-within` switches to `text-blue-600`, input `pl-9`):

```html
<div class="group relative">
  <span class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint transition-colors duration-150 group-focus-within:text-blue-600">
    <Icon name="user" size={14} />
  </span>
  <input id="login-username" class="field-input h-9 pl-9" ... />
</div>
```

Password input is the same shape (icon `lock`), with a password-visibility toggle button on the right:

```html
<button type="button" class="absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-ink-faint transition-colors duration-150 hover:bg-subtle hover:text-ink-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white" aria-label={...} aria-pressed={showPassword}>
  <Icon name={showPassword ? 'eye-off' : 'eye'} size={14} />
</button>
```

(The input uses `pr-11` to make room for the button; existing `aria-label` / `aria-pressed` behavior is kept.)

**④ Error message**

danger combination (00 §2.3; text on soft backgrounds always uses the deep step):

```html
<div class="flex gap-2.5 rounded-lg border border-danger/25 bg-danger-soft px-3.5 py-3 text-[13px] leading-5 text-danger-deep" role="alert">
  <Icon name="warning" size={14} className="mt-0.5 shrink-0" />
  <span>{error}</span>
</div>
```

**⑤ Submit button (primary · lg step)**

00 §7.1 primary variant + `h-9 w-full` (the lg size only varies button height; the radius stays `rounded-lg`):

```html
<button type="submit" class="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-3 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-blue-700 active:bg-blue-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400" disabled={submitting}>
  {submitting
    ? <><span class="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-white/40 border-t-white" />Verifying identity</>
    : <>Sign in to workbench<Icon name="arrow-right" size={14} class="transition-transform duration-150 group-hover:translate-x-0.5" /></>}
</button>
```

(The existing small light-on-dark spinner matches the 00 §7.10 dark-background spec and is kept; remove the existing brand-colored drop shadow on the button, `shadow-[0_10px_25px_...]` - outside the five-step 00 shadow scale.)

**⑥ Bottom security note + role chips**

`mt-7 border-t border-line-soft pt-5`; note text `flex items-start gap-2.5 text-[12px] leading-5 text-ink-muted` + `lock` icon at 13px. Role chips use 00 §7.5:

```html
<span class="inline-flex h-6 items-center rounded-md border border-line bg-card px-2 font-mono text-[11px] text-ink-muted">viewer read-only</span>
```

## 4. Component State Specs

| Component | default | hover | active / focus | disabled / loading | selected |
|---|---|---|---|---|---|
| Username/password input | `.field-input h-9`: `border-line bg-card/60`, placeholder `text-ink-faint` | `border-line-strong` | `border-blue-600 bg-card + ring-2 ring-blue-600/15` (00 §7.2) | `opacity-50 cursor-not-allowed` (disabled while submitting) | - |
| Left icon | `text-ink-faint` | follows input hover | `focus-within` `text-blue-600` | follows input | - |
| Password visibility toggle | `text-ink-faint`, no background | `bg-subtle text-ink-soft` | shared focus ring (same spec as §3.3⑤) | - | at `aria-pressed=true` the icon switches eye/eye-off (only the icon changes visually) |
| Submit button | `bg-blue-600 text-white` | `bg-blue-700` | `active:bg-blue-800`; shared focus ring spec | `bg-slate-200 text-slate-400 cursor-not-allowed` + spinner | - |
| notice / error bars | warning / danger soft+deep (static) | - | - | - | - |
| Role chip | `border-line bg-card text-ink-muted` | - | - | - | - |
| Version chip (left column) | `border-blue-700 text-blue-200` | - | - | - | - |

## 5. Data States

| State | Design |
|---|---|
| Initial | Empty form; username `autoFocus` (existing behavior kept); placeholders "Enter username" / "Enter password" |
| Client-side validation failure | `error` bar (danger combination, `role="alert"`) with the text "Enter your username and password"; the inputs keep whatever the user has typed |
| notice (expired / logged out) | warning bar above the form (`role="status"`), mutually exclusive with `error` (notice comes from props, error is local state; existing logic unchanged) |
| Submitting | Button disabled + spinner (small, `border-white/40 border-t-white`) + text "Verifying identity"; both inputs disabled in sync |
| Server error | The ApiError message or "Cannot reach the service, please try again later" goes into the error bar; the button returns to default |
| Success | No transition animation; switches straight to Workspace (existing behavior, no extra transition designed) |

## 6. Interaction and Motion

| Interaction | Motion (00 §5) |
|---|---|
| Headline area / illustration area entrance | `animate-fade-up` (300ms `out-quint`; the existing two-step `animation-delay: 0 / 120ms` stagger is kept, with the current delay values) |
| Input hover/focus | `transition-all duration-150` (built into `.field-input`) |
| Submit button hover/active | `transition-colors duration-150` |
| Icon movement (submit button arrow) | `transition-transform duration-150`, hover `translate-x-0.5` (kept) |
| Password toggle / left icon color change | `transition-colors duration-150` |
| Spinner | `animate-spin` (Tailwind built-in 1s; a continuous loading-semantics animation, the third kind allowed beyond 00 §5.2: the regular button-loading case) |
| All | Globally disabled under `prefers-reduced-motion` (existing index.css rule, 00 §8.2(5) retained) |

## 7. Change List for Existing Components

The development agent executes these one by one; all "same-name, new-value" tokens (`shadow-float`, `line`, `ink` family, etc.) are replaced globally per 00 §8/§9, so the table below lists only page-level changes beyond the 00 mapping.

| # | Component - current - target - tokens/classes involved |
|---|---|
| 1 | `LoginPage.tsx` - root container `bg-canvas` + `bg-fine-grid bg-grid-28` grid layer + left `bg-pine-200/30 blur-3xl` glow orb - change to `bg-page`, remove both decorative layers - `bg-page`; drop `bg-fine-grid` |
| 2 | `LoginPage.tsx` - card `rounded-[24px]` - change to `rounded-2xl` (00 §4.2 login card 16px step) - `rounded-2xl` |
| 3 | `LoginPage.tsx` - left column `bg-pine-900` + white 34px grid overlay + two blur glow orbs (`pine-500/30`, `ember/20`) - change to `bg-blue-900`, remove all three decorative layers - `bg-blue-900` |
| 4 | `LoginPage.tsx` - brand panel `BrandMark className="text-pine-600"`, name `font-display text-[22px]`, slogan `text-[#8fb0a3] text-[9px]`, chip `border-white/15 text-[#a8c4b8] text-[9px]` - change to `text-blue-600` mark (legible on the dark background, see §3.2①) / `font-sans text-[20px] font-semibold tracking-tight text-white` + `text-blue-300` suffix / `text-[11px] text-blue-300` / `border-blue-700 text-blue-200 text-[11px]` - `blue-600`, `blue-700/200/300`, `text-white` |
| 5 | `LoginPage.tsx` - headline `font-display text-[46px] xl:text-[55px] font-medium tracking-[-0.035em] text-[#f5f1e7]` - change to `text-[28px] font-bold leading-[1.25] tracking-tight text-white` (00 §3.2 exception step + §3.3 weight 700) - `text-[28px]`, `font-bold`, `text-white` |
| 6 | `LoginPage.tsx` - subcopy `text-[13px] text-[#a9c0b6]`, eyebrow `text-pine-300 text-[10px]`, eyebrow rule `bg-pine-400` - change to `text-blue-100` / `text-blue-300 text-[11px]` / `bg-blue-400` - `blue-100/300/400`, `text-[11px]` |
| 7 | `MiniNode` (inside LoginPage) - `border-pine-300`, header `bg-[#203f36]`, title `text-pine-700 / text-[#dbe9e2]`, fields `text-ink-soft`, collapsed text `text-ink-faint`, font sizes 9.5/8px - change to the dark-background spec (§3.2③ table): idle `border-blue-700 bg-blue-800`, active `border-blue-300` header `bg-blue-700`, title `text-blue-100`/`text-white`, fields `text-blue-200`, collapsed text `text-blue-300`; font size unified to `text-[11px]` - `blue-200/300/700/800`, `text-[11px]` |
| 8 | `LoginPage.tsx` - illustration SVG connectors `#5c8f7b / #7fa898 / #2f64d8`, dots `#b3d9c7 / #2f64d8` - imported line `#93C5FD` (blue-300), AI dashed line `#EEF2FF` (ai-soft), dots `#BFDBFE` / `#EEF2FF` - `blue-300`, `blue-200`, `ai-soft` |
| 9 | `LoginPage.tsx` - bottom info bar `border-white/10 bg-[#173b31]/85`, icon block `bg-pine-500/20 text-pine-200`, text `#d5e6de / #8fb0a3` at 8.5px - change to `border-blue-700 bg-blue-800/85`, `bg-blue-700/60 text-blue-200`, `text-blue-100 / text-blue-300` `text-[11px]` - `blue-700/800`, `blue-100/200/300`, `text-[11px]` |
| 10 | `LoginPage.tsx` - three-feature grid divider `border-white/10`, number `text-pine-400 text-[9px]`, title `text-[#dbe8e2] text-[11px]`, description `text-[#7f9e91] text-[8.5px]` - change to `border-blue-700` / `text-blue-300 text-[11px]` / `text-white text-[12px]` / `text-blue-300 text-[11px]` - `blue-300/700`, `text-white`, `text-[11px]/text-[12px]` |
| 11 | `LoginPage.tsx` - right column eyebrow rule `bg-pine-600`, eyebrow `text-pine-700 text-[9.5px]` - change to `bg-blue-600` / `text-blue-700 text-[11px]` - `blue-600/700`, `text-[11px]` |
| 12 | `LoginPage.tsx` - title "Back to the lineage scene" `font-display text-[36px] font-medium tracking-[-0.03em]` - change to `text-2xl font-semibold tracking-tight text-ink` (00 §3.2 login page main title step 24px + §3.1 serif removal) - `text-2xl`, `font-sans` |
| 13 | `LoginPage.tsx` - input `field-input h-11 pl-10` (icon 15px at `left-3.5`) - change to `field-input h-9 pl-9` (00 §4.5 input 36px + §7.2 icon spec), icon 14px at `left-3` - `h-9`, `pl-9` |
| 14 | `LoginPage.tsx` - input icon `focus-within` `text-pine-600` - change to `text-blue-600` - `blue-600` |
| 15 | `LoginPage.tsx` - password toggle button `hover:bg-line-soft`, focus ring `ring-pine-500/40` - change to `hover:bg-subtle`, shared focus ring (00 §7.1) - `bg-subtle`, `ring-blue-600/60` |
| 16 | `LoginPage.tsx` - notice bar `border-ochre/20 bg-ochre-soft text-ochre-deep` - change to the warning combination (00 §2.3) - `border-warning/25 bg-warning-soft text-warning-deep` |
| 17 | `LoginPage.tsx` - error bar `border-rosewood/20 bg-rosewood-soft text-rosewood-deep` - change to the danger combination - `border-danger/25 bg-danger-soft text-danger-deep` |
| 18 | `LoginPage.tsx` - submit button `h-11 rounded-xl bg-pine-800` + brand-colored shadow + `disabled:opacity-65` + `font-semibold` - change to `h-9 rounded-lg bg-blue-600` with all four states (§3.3⑤), remove the shadow, neutralize disabled (00 §7.1 primary) - `bg-blue-600/700/800`, `disabled:bg-slate-200 disabled:text-slate-400` |
| 19 | `LoginPage.tsx` - role chips `rounded-full border-line-soft bg-canvas/70 text-[9px]` - change to the 00 §7.5 chip: `rounded-md h-6 border-line bg-card px-2 font-mono text-[11px] text-ink-muted` - `rounded-md`, `bg-card`, `text-[11px]` |
| 20 | `Brand.tsx` - `BrandMark` hard-coded colors `#b3d9c7 / #f3f0e7 / #83bfa6` (hard-coded beige-green) - dots become `#BFDBFE` (blue-200) and `#FFFFFF`, connectors `#93C5FD` (blue-300), center dot `#FFFFFF`; the `currentColor` base-block mechanism is unchanged - `blue-200`, `blue-300`, `white` |
| 21 | `Brand.tsx` - `Brand` name `font-display text-[21px]`, "Lite" `text-pine-600`, slogan `text-[9px]` - change to `font-sans text-base font-semibold tracking-tight text-ink`, "Lite" `text-blue-600`, slogan `font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint` (this component's use in TopBar is covered in document 02; on the dark background of the login page the caller overrides the text color) - `text-base`, `blue-600`, `text-[11px]` |

## 8. Accessibility Notes (Page-Specific)

1. **Initial focus**: `autoFocus` on the username input (kept); Tab order: username -> password -> visibility toggle -> submit button, with no focus trap.
2. **Bar semantics**: notice `role="status"`, error `role="alert"` (kept as is), so screen readers can tell a "notice" from an "error".
3. **Errors are not conveyed by color alone**: the danger bar has both a `warning` icon and text (00 §10.6).
4. **Contrast spot checks** (combinations in the 00 §2.6 table): `blue-100` on `blue-900` (dark-background body text), `white` on `blue-600` (submit button), `warning-deep` on `warning-soft`, `danger-deep` on `danger-soft` - the first three combination rules still need to be written back into 00 (see next section); verify >=4.5:1 with a color picker before delivery.
5. **Password toggle**: `aria-pressed` expresses the on/off state (kept); hit area 28x28 >= 24x24.
6. **`autoComplete`**: `username` / `current-password` (kept), for password manager support.
7. **Entrance animation**: the 300ms `fade-up` is globally disabled under `prefers-reduced-motion` (covered by the index.css rule).

## Tokens to Be Added (Recommended for Write-Back to 00)

| # | Gap | Suggested value (all composed from existing tokens) | Notes |
|---|---|---|---|
| 1 | Text three-tier rules on the dark panel (blue-900 background) | title `white` / body `blue-100` / secondary and eyebrow `blue-300` (WCAG calculation: white on blue-900 is about 10.4:1, blue-100 about 8.5:1, blue-300 about 5.7:1, all >=4.5:1) | 00 §2.1 only defines the background use of blue-900, not text hierarchy combinations on dark backgrounds; this page depends on them in many places, so adding a "text on dark backgrounds" subsection to 00 §2.2 is recommended |
| 2 | Surface step for illustration cards nested on dark backgrounds | card `bg-blue-800` + `border-blue-700`, active header `bg-blue-700` | 00 has no step for "nested surfaces on dark backgrounds"; recommend folding it into the subsection above |
| 3 | Step for decorative dividers / chip borders on dark backgrounds | `border-blue-700` | Replaces the existing `white/10` and `white/15` (out-of-scale opacity combinations); recommend write-back |

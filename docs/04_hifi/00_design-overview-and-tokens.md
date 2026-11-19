# 00 · Design Overview and Design Token

> Purpose: the foundation document for the hi-fi design specs in `docs/04_hifi/`. It defines the color, typography, spacing, motion, layering, and shared component specifications of the Clew frontend, for direct reference by page design documents 01–06 and direct execution by the formal frontend development in `frontend/`. Every token in this document is precise enough to "copy into code": color values, font sizes, durations, and class-name combinations are final values, and page documents and implementation must not deviate. If a change is needed, update this document first, then sync downstream.
>
> **2026-10 Clew brand redesign** (user-confirmed): product name LineageLite → **Clew** (yarn-ball/clue metaphor); the brand primary blue scale is switched wholesale to `brand` (Tailwind orange, yarn-ball orange); the field tracking chain focus changes from red to brand orange (the "light the clue" brand moment); danger red is reserved only for deletion/validation failure; lineage manual edges change from amber to teal (yielding to brand orange); warning is deepened one step to separate it from brand orange. Because white text on orange-600 lacks sufficient contrast, solid button tiers move up as a whole from 600/700/800 to **700/800/900**. All color values in this document have been rewritten accordingly; the old blue tiers survive only in the historical rows of "Basis and Sources".
>
> Scope: React 19 + TypeScript + Vite + Tailwind CSS v3 + `@xyflow/react`, no UI component library, component source bundled in-repo, no new dependencies. Light mode only (white background), no dark mode.

---

## 0. Basis and Sources

| Basis | Purpose |
|---|---|
| User constraints (highest priority) | White background + yarn-ball orange primary color (upgraded from blue with user confirmation in 2026-10; see the redesign note at the top); Data-Dense Dashboard style (density 8/10: restrained, professional, data readability first); hard accessibility requirements (body text contrast ≥4.5:1, visible focus ring, prefers-reduced-motion, 150–300ms transitions) |
| ui-ux-pro-max retrieved color baseline | Primary `#1E40AF`, Secondary `#3B82F6`, Background `#F8FAFC`, Card `#FFFFFF`, Muted `#E9EEF6`, Muted Foreground `#475569`, Border `#DBEAFE`, Destructive `#DC2626`, Accent/CTA `#D97706`, Ring `#1E40AF` (any fine-tuning within the baseline is annotated with its rationale in this document) |
| `prototype/frontend/tailwind.config.cjs`, `src/index.css` | Existing token structure and naming (canvas/surface/ink/line/pine/ember/ochre/ai/rosewood, boxShadow, keyframes); this document produces their complete replacement and the old→new mapping (§8, §9) |
| `docs/03_dev/02_frontend-development.md` | §1 tech stack, §6 component inventory (22), §7 canvas implementation (`getEdgeVisual` four forms, node card structure, handle system) |
| `docs/02_prototype/clew-lofi-prototype.html` | Lo-fi 6-screen information architecture baseline (lineage canvas / source file preview / import wizard / AI chat / versions and users / sign-in) |
| Representative component source | `LoginPage.tsx`, `DatasetNode.tsx`, `TopBar.tsx`, `LineageEdge.tsx` (getEdgeVisual), `SourceBadge.tsx`, `Icon.tsx` |
| WCAG 2.1 | Relative luminance formula computed by hand; all text combinations' contrast ratios are in the §2.6 verification table |

All contrast ratios in this document are computed with the WCAG relative luminance formula (ratios rounded to two decimals): body text ≥4.5:1; large text (≥18.66px bold or ≥24px) and graphics/UI components ≥3:1.

---

## 1. Design Positioning and Principles

### 1.1 Product Character

Clew is a **B2B internal data tool**: the data team opens it every day to verify "where this data comes from". The interface character is that of a **professional data tool**—like a precision instrument, not a marketing page. Users stare at the canvas and tables for tens of minutes at a time, so the visual system must be low-noise, high signal-to-noise, and comfortable for long viewing without fatigue.

Style anchor: **Data-Dense Dashboard** (density 8/10). High information density yet orderly: white background, thin-border layering, a restrained yarn-ball orange primary, no decorative gradients or glows, sans-serif type, compact controls.

### 1.2 Design Principles (Executable, 5)

1. **Data ink first**: screen pixels are allocated to the data itself first (lineage graph, fields, locators). Borders, shadows, and icons are layering devices, not decoration; large-area gradients, glows, and illustrative decoration are prohibited (the blur-orb decoration on the current sign-in page is removed in hi-fi).
2. **White surfaces + one light-gray page**: content always sits on white cards; the page background `#F8FAFC` only serves to set the cards off. Never nest more than two surface levels (page → card → subtle row background).
3. **Brand orange only for interaction and identity**: brand orange (the `brand` scale) expresses "clickable, selected, current, brand"; data content is always neutral gray ink. Brand orange covers no more than ~10% of the screen; the tracking chain is the only exception (see §2.4 focus).
4. **States must be distinguishable**: lineage source (imported/manual/ai), role, and success/warning/danger each have a fixed three-tier color set (DEFAULT/soft/deep) and are not mixed; body text on soft backgrounds always uses the deep tier.
5. **Motion serves feedback, not performance**: transitions are used only for state changes (hover, expand, overlay entrance), 150–300ms; only two continuous animation semantics remain (AI suggestion edge flow, skeleton pulse), and they respect `prefers-reduced-motion`.

### 1.3 Light/Dark Strategy

**Light mode only**, white background. No dark theme, no `light-dark()` branches (the dark values in the lo-fi prototype serve only its self-demo and do not enter the hi-fi system). Rationale: for a single-operator internal tool, the doubled token maintenance cost of dark mode far outweighs the benefit; a white background is the most reliable reading environment for data verification (tables, locators, code).

---

## 2. Color System (Design Token Core)

### 2.1 Primary Color brand (Clew Yarn-Ball Orange, 50–900)

Clew redesign (2026-10, user-confirmed): the brand primary switches wholesale from the blue scale to the Tailwind v3 standard orange scale (token name `brand`), forming a "cool gray base + warm orange accent" with the slate neutral surfaces and giving it distinction among data tools crowded with blue and purple. **Solid buttons and brand body text use 700 (white text 5.18:1); 600 is only a graphic color**—white on orange-600 is only 3.56:1 (old brand-600 was 5.17:1). This is the most critical tier-rule change of this recolor.

| Token | Color value | Purpose (sole or primary) |
|---|---|---|
| `brand-50` | `#FFF7ED` | Field tracking row background, seed node header background, light orange hover emphasis |
| `brand-100` | `#FFEDD5` | Light-background emphasis: table-level handle hover background, `::selection` background, light orange outline |
| `brand-200` | `#FED7AA` | Seed node header border, light orange outline |
| `brand-300` | `#FDBA74` | Canvas decorative lines (sign-in page illustration), secondary text on dark panels |
| `brand-400` | `#FB923C` | Secondary graphics: yarn-ball logo winding line, minor graphic accents (never text) |
| `brand-500` | `#F97316` | Purely decorative accents (wordmark thread-end dot, list dots); **carrying information is prohibited** (2.8:1 on white) |
| `brand-600` | `#EA580C` | **Primary graphic color**: field tracking chain (lineage-focus), handle hover, seed top strip, icon tile, ring outline (white text 3.56:1 → body text and solid buttons prohibited) |
| `brand-700` | `#C2410C` | **Primary interaction**: primary button default, brand/link text, tracked field name text |
| `brand-800` | `#9A3412` | Primary button hover, brand deep emphasis (logo container background, badge deep text) |
| `brand-900` | `#7C2D12` | Sign-in page left dark panel background, primary button active |

### 2.2 Neutral Colors: Surfaces and Text

Three surface levels (bottom to top) + four text tiers + three border tiers, all in the slate family (same family as the `#F8FAFC`/`#475569` baseline).

**Surfaces**

| Token | Color value | Purpose |
|---|---|---|
| `page` | `#F8FAFC` | Page background, canvas background (baseline Background, slate-50) |
| `card` | `#FFFFFF` | Cards, panels, modals, drawers, node cards (baseline Card, pure white) |
| `subtle` | `#F1F5F9` | Secondary surface: table header rows, code block background, hover row background, skeleton (slate-100) |

> The baseline Muted `#E9EEF6` is fine-tuned to `#F1F5F9` (slate-100): it stays in the same slate family as the other neutrals, avoiding a third gray tone; the visual difference is negligible.

**Text (four ink tiers, naming consistent with the existing structure)**

| Token | Color value | Purpose | On card contrast | On page |
|---|---|---|---|---|
| `ink` | `#0F172A` | Primary text: headings, primary table content, node titles (slate-900) | 17.9:1 | 17.1:1 |
| `ink-soft` | `#334155` | Secondary text: body paragraphs, form values, menu items (slate-700) | 10.4:1 | 9.9:1 |
| `ink-muted` | `#475569` | Supporting text: descriptions, table headers, metadata (= baseline Muted Foreground, slate-600) | 7.6:1 | 7.2:1 |
| `ink-faint` | `#64748B` | Placeholder, disabled supporting text, timestamps, `kbd` (slate-500) | 4.76:1 | 4.55:1 |

Hard rule: `ink-faint` on `subtle` (#F1F5F9) is 4.34:1 and **does not pass**—body text on subtle backgrounds uses at least `ink-muted`; `ink-faint` is used only on white/page backgrounds or as a placeholder (non-essential information).

**Borders (three line tiers)**

| Token | Color value | Purpose |
|---|---|---|
| `line` | `#E2E8F0` | Default border: cards, input resting state, emphasized dividers (slate-200) |
| `line-strong` | `#CBD5E1` | Strong border: input/card hover, table outer frame, scrollbar (slate-300) |
| `line-soft` | `#F1F5F9` | Weak divider: in-card row dividers, section lines (= same value as subtle; separate name kept for semantic substitution) |

> The baseline Border `#DBEAFE` (brand-100) is fine-tuned to slate-200 as the default border: `#DBEAFE` is only 1.22:1 against white, too light as a global border, and would make the whole UI too blue (after the Clew redesign the blue tiers are deleted; the former "blue-semantic" light outlines are now carried by brand-100/200).

### 2.3 Semantic Colors (Three Tiers per Group: DEFAULT / soft / deep)

Aligned with the existing ember/ochre/ai three-tier structure. **Usage rules: soft is the background; deep is the text and icons on soft backgrounds; DEFAULT is the icon/text on white backgrounds and the background of solid buttons**. The DEFAULT of warning and danger falls short of 4.5:1 on their respective soft backgrounds, so deep is always used on soft backgrounds (see §2.6).

| Semantic | DEFAULT | soft | deep | Scenario |
|---|---|---|---|---|
| `success` | `#15803D` | `#F0FDF4` | `#166534` | Success toast, confirmed state, validation passed (green-600/50/800) |
| `warning` | `#B45309` | `#FFFBEB` | `#92400E` | Low confidence, sign-in expired notice (Clew redesign: DEFAULT deepened from amber-600 #D97706 to amber-700 to avoid on-screen confusion with brand orange; manual lineage edges have switched to teal, see §2.4) |
| `danger` | `#DC2626` | `#FEF2F2` | `#B91C1C` | Errors, deletion confirmation, locator invalidation (= baseline Destructive, red-600/50/700; after the Clew redesign red carries only danger semantics, no longer tracking) |
| `info` | `#2563EB` | `#EFF6FF` | `#1E40AF` | General notices, import batch status (after the Clew redesign info keeps blue, as a semantic color only, no longer carrying the brand) |

### 2.4 Functional Colors: AI Badge Color and Lineage Edge Source Colors

**AI color (`ai` three tiers, independent of the primary blue)**

| Token | Color value | Purpose |
|---|---|---|
| `ai` | `#4F46E5` | AI identity color: AI suggestion edges, sparkles icon, AI badge dot (indigo-600) |
| `ai-soft` | `#EEF2FF` | AI badge background, light background of AI-related panels (indigo-50) |
| `ai-deep` | `#3730A3` | AI badge text, AI-related body text on soft backgrounds (indigo-800) |

> Decision: **do not share with the primary color**. The old value `#2F64D8` had almost the same luminance as the then-primary blue `#2563EB` and was indistinguishable side by side; yet "AI suggestion = unconfirmed" is the most critical state semantic in this product, requiring color redundancy beyond dashed lines + flow animation. The indigo family was chosen (the AI color is used only in small accents). Contrast: `#4F46E5` on white 6.29:1, on `#EEF2FF` 5.62:1, both usable for body text. After the Clew redesign the primary is orange, so the indigo AI color is even more distinct from the primary and stays unchanged.

**Lineage edge source colors (`lineage` group, aligned with the four forms of `getEdgeVisual` in `LineageEdge.tsx`)**

Edge colors go directly into the SVG `stroke`; they are defined as the `lineage` color group for constant reference by `getEdgeVisual` (avoiding scattered hex). The four forms keep their existing line style/width unchanged; only the color values are replaced:

| Form (getEdgeVisual branch) | Old color | New token / color value | Line style | Width | On page contrast (graphics ≥3:1) |
|---|---|---|---|---|---|
| `source='ai'` (AI suggestion) | `#2f64d8` | `lineage-ai` = `#4F46E5` | Dashed `6 5` | 1.8 | 6.0:1 ✓ (`animated` flow retained) |
| `source='manual'` (manually confirmed) | `#a36b11` → `#D97706` | `lineage-manual` = `#0D9488` (teal-600; Clew redesign: former amber yields to brand orange) | Field-level solid; table-level dashed `4 5` | 1.7 | 3.58:1 ✓ |
| imported field-level | `#52645c` | `lineage-imported` = `#475569` | Solid | 1.55 | 7.2:1 ✓ |
| imported table-level | `#8b958f` | `lineage-imported-weak` = `#64748B` | Dashed `4 5` | 1.4 | 4.55:1 ✓ |
| Same-name field matching (derived, view-derived) | — (new) | `lineage-derived` = `#94A3B8` | Dotted `2 4` | 1.3 | 2.46:1 ✗ (see note 2 below) |
| Field tracking highlight (focusState='chain') | `#DC2626` | `lineage-focus` = `#EA580C` (= brand-600, the "light the clue" brand moment) | Reuses the original line style | 2.6 | 3.40:1 ✓ (`animated` flow) |

> The old imported table-level color `#8b958f` is only 2.45:1 on `#F8FAFC` (below the 3:1 graphic minimum); it is changed to `#64748B`, staying weaker than field-level edges by "dashed + thinner".
>
> Note 2: `lineage-derived` is the **view-derived helper line** for "same-name field matching at both ends of table-level lineage" (not persisted, not selectable), deliberately weaker than all persisted edges. 2.46:1 being below the 3:1 graphic minimum is a **known trade-off**: the same-name matching relationship can be fully read from the field names at both ends, the tooltip text, and the legend, so the line itself carries no unique information (WCAG 1.4.11 applies to graphics "required to understand the content"). If review requires compliance, add a darker tier to this table and then change `lib/edgeColors.ts` [TBD-UX, handle in the confirmation phase]. Since the Clew redesign, `lineage-focus` has the same value as the brand primary: tracking = the "light the clue" brand moment (a positive action), not error semantics; danger red is reserved only for deletion/validation failure. Orange (tracking) and red (danger) are adjacent hues, distinguished by form—tracking chains are 2.6 wide + flow animation + all other edges dimmed by 0.15, while danger appears only in small controls and copy.

### 2.5 Canvas-Specific Specifications

| Element | Specification |
|---|---|
| Canvas background | `bg-page` (`#F8FAFC`) + dot grid: `backgroundImage: radial-gradient(circle, rgba(148,163,184,0.35) 1px, transparent 1px)`, `backgroundSize: 24px 24px` (tokens: `bg-dot-grid bg-grid-24`; replaces the old square grid `fine-grid`—a dot grid is lighter than line grids, so the Data-Dense canvas has less noise) |
| Node card | `bg-card` + `border-line-strong` (hover converges to `shadow-card`); width 288px, corner radius `rounded-xl` (12px) unchanged (`lib/layout.ts` constants untouched) |
| Seed node | Top 2px accent strip `bg-brand-600/80`; header background `bg-brand-50`, header border `border-brand-200`; "seed" badge `text-brand-800`; `shadow-node-active` |
| Node selected | `shadow-node-active` (1.5px brand-600 outer ring + deep orange shadow, see §4.4); keyboard focus uses a 2px `brand-600/65` outline + 3px offset |
| Node header (non-seed) | Background `bg-subtle`, bottom border `border-line-soft` |
| Field row | Hover background `bg-subtle/70` (Clew redesign: ordinary hover uses neutral gray; `brand-50` is reserved for tracked rows so non-matching rows are not misread as part of the chain); field name turns `text-brand-800` on hover; tracked row background `bg-brand-50` (focused `ring-1 ring-brand-300/80`) |
| Table-level handle | 9px square (r2): white background + `border-line-strong`; hover `border-brand-700 bg-brand-100` + brand ring |
| Field-level handle | 7px dot: white background + `border-line-strong`, opacity 0.55; on node hover / self hover `border-brand-600 bg-brand-50` opacity 1; tracked state `field-handle-traced` is also brand-600/brand-50 |
| Controls / MiniMap | White background, `border-line`, `rounded-lg`, `shadow-float`; button hover `bg-page text-brand-700`; MiniMap seed node color `#EA580C`, normal `#CBD5E1` |
| Edge tooltip card | White background, `border-line`, `rounded-lg`, `shadow-float` (replaces the original React Flow default style) |

### 2.6 Contrast Verification Table (WCAG 2.1 Calculations)

**Body text (requires ≥4.5:1)**

| Foreground | Background | Ratio | Result |
|---|---|---|---|
| `ink` #0F172A | card #FFFFFF | 17.90 | ✓ |
| `ink` | page #F8FAFC | 17.06 | ✓ |
| `ink-soft` #334155 | #FFFFFF | 10.36 | ✓ |
| `ink-soft` | #F8FAFC | 9.90 | ✓ |
| `ink-muted` #475569 | #FFFFFF | 7.58 | ✓ |
| `ink-muted` | #F8FAFC | 7.24 | ✓ |
| `ink-muted` | subtle #F1F5F9 | 6.92 | ✓ |
| `ink-faint` #64748B | #FFFFFF | 4.76 | ✓ |
| `ink-faint` | #F8FAFC | 4.55 | ✓ (lower bound; used only for placeholders/metadata) |
| `ink-faint` | subtle #F1F5F9 | 4.34 | ✗ combination prohibited; use ink-muted on subtle backgrounds |
| brand-600 #EA580C | #FFFFFF | 3.56 | ✗ no text/solid buttons (graphics and icon tiles only) |
| brand-700 #C2410C (link/brand text) | #FFFFFF | 5.18 | ✓ |
| brand-800 #9A3412 | #FFFFFF | 7.31 | ✓ |
| brand-700 | brand-50 #FFF7ED | 4.88 | ✓ (tracked field names) |
| brand-800 | brand-50 #FFF7ED | 6.88 | ✓ (badges/hovered field names) |
| white | brand-700 (primary button default) | 5.18 | ✓ |
| white | brand-800 (primary button hover) | 7.31 | ✓ |
| white | brand-900 (primary button active) | 9.37 | ✓ |
| white | danger #DC2626 (danger button) | 4.83 | ✓ |
| success #15803D | #FFFFFF | 5.02 | ✓ |
| warning #B45309 | #FFFFFF | 5.02 | ✓ (new DEFAULT after the Clew redesign) |
| ai #4F46E5 | #FFFFFF | 6.29 | ✓ |

**Soft-background badges/notices (deep-tier body text, requires ≥4.5:1)**

| Foreground | Background | Ratio | Result |
|---|---|---|---|
| success-deep #166534 | success-soft #F0FDF4 | 6.81 | ✓ |
| warning-deep #92400E | warning-soft #FFFBEB | 6.84 | ✓ |
| danger-deep #B91C1C | danger-soft #FEF2F2 | 5.91 | ✓ |
| info-deep #1E40AF | info-soft #EFF6FF | 8.01 | ✓ |
| ai-deep #3730A3 | ai-soft #EEF2FF | 8.88 | ✓ |
| warning #D97706 | warning-soft #FFFBEB | 3.07 | ✗ prohibited (hence the rule: use deep on soft backgrounds) |
| danger #DC2626 | danger-soft #FEF2F2 | 4.41 | ✗ prohibited (same as above) |

**Graphics / UI components (requires ≥3:1)**

| Graphic | Background | Ratio | Result |
|---|---|---|---|
| lineage-imported #475569 | #F8FAFC | 7.24 | ✓ |
| lineage-imported-weak #64748B | #F8FAFC | 4.55 | ✓ |
| lineage-manual #0D9488 | #F8FAFC | 3.58 | ✓ (Clew redesign: teal-600) |
| lineage-ai #4F46E5 | #F8FAFC | 6.01 | ✓ |
| lineage-focus #EA580C | #F8FAFC | 3.40 | ✓ (2.6px line + flow animation; Clew redesign = brand-600) |
| lineage-derived #94A3B8 | #F8FAFC | 2.46 | ✗ known trade-off: view-derived helper line; information is redundantly carried by field names/tooltip/legend (§2.4 note 2) |
| brand-600 #EA580C (ring/selection outline) | #FFFFFF | 3.56 | ✓ graphic; ✗ must not be used as white-background text (body text uses brand-700) |
| input border line #E2E8F0 | #FFFFFF | 1.23 | known trade-off: resting input recognition relies on the placeholder and shape (industry-common, like GitHub/Linear); the focus-state border brand-600 reaches 3.56:1 (graphic-level pass). Honestly logged in the accessibility checklist (§10) |

> Disabled elements are not required by WCAG to meet contrast; uniformly use `opacity-50` or neutral gray (see §7.1).

---

## 3. Typography System

### 3.1 Font Families (2 families, converged from 3)

| Token | Font stack | Purpose |
|---|---|---|
| `font-sans` | `'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif` | All interface text (mixed Chinese/English, headings, buttons) |
| `font-mono` | `'IBM Plex Mono', 'SFMono-Regular', Menlo, Consolas, monospace` | Dataset IDs, field names, locators, code/JSON, numeric statistics (with `tabular-nums`), `kbd` |

> **Decision: remove the serif display family** (Newsreader / Noto Serif SC / Songti SC). Rationale: (1) Data-Dense Dashboard requires restraint and no decoration; the editorial/literary character of serif conflicts with the "professional data tool" positioning; (2) an all-sans UI makes the sign-in page headline continuous in character with the workspace, avoiding a "marketing page → tool page" break; (3) one fewer Google Fonts family to load (Newsreader + Noto Serif SC is roughly 100KB+), so the intranet tool loads faster. The former `font-display` scenario (sign-in page headline) switches to `font-sans` + 24–28px + `font-semibold` + `tracking-tight`. The two families are also removed from the Google Fonts `@import` (§8.2).

Chinese primarily uses Noto Sans SC (four weights 400/500/600/700, ready on load); monospace is always IBM Plex Mono (400/500/600). Introducing further font families is **prohibited**.

### 3.2 Font Size Scale (8 steps, converging fragmented values)

Existing code has severe font-size fragmentation (15+ values from 7.5–55px). Unify them into the following 8 steps + notation conventions. Default Tailwind steps use the default classes; non-default steps use arbitrary-value notation:

| Step | Notation | Purpose | Line height |
|---|---|---|---|
| 11 | `text-[11px]` | Badges, node IDs, `kbd`, mono metadata | `leading-4` (16px) |
| 12 | `text-xs` | Secondary body, table cells, sidebar entries, labels | `leading-4`/`leading-[18px]` |
| 13 | `text-[13px]` | **Default control font size**: buttons, inputs, menu items, body text (the body anchor at density 8) | `leading-5` (20px) |
| 14 | `text-sm` | Emphasized body, form descriptions, tooltip body | `leading-5` |
| 16 | `text-base` | Card titles, section titles (h2/h3) | `leading-6` (24px) |
| 18 | `text-lg` | Modal/drawer titles, statistics | `leading-6` |
| 20 | `text-xl` | Sign-in page subtitle, empty-state main copy | `leading-7` |
| 24 | `text-2xl` | Sign-in page main title (may add `tracking-tight`) | `leading-8` (32px) |
| 28 (exception) | `text-[28px]` | Only the left-column main slogan on the sign-in page | `leading-[1.25]` |

Rule: field names inside node cards are uniformly `text-[11px] font-mono` (old 10.5px/8.5px converge to the 11px/12px steps); **font sizes outside the scale are prohibited** (page documents must not invent 15px, 22px, etc.).

### 3.3 Font Weight Rules

| Weight | Scenario |
|---|---|
| 400 | Body text, table content, descriptive text (default; do not write `font-normal`) |
| 500 | Buttons, menu items, form labels, badge text, node titles, table headers |
| 600 | Section/card titles, modal and drawer titles, page h1 (small titles stand out via 600) |
| 700 | Only two places: the sign-in page main slogan and large statistics (18px+). 700 is prohibited at small sizes (looks blurry) |

### 3.4 Typography Details

- Numbers (statistics, confidence, counts) always use `font-mono tabular-nums` to keep lists aligned.
- Locators, field names, and dataset IDs always use `font-mono`; in mixed Chinese descriptions, mono wraps only the code portion.
- `tracking-tight` (-0.025em) is used only for ≥20px headings; body text and mono get no letter spacing.
- Long IDs/locators use `truncate` + a `title` hint; they must not wrap and break the card.

---

## 4. Spacing, Radius, Borders, Shadows, and Dimensions

### 4.1 Spacing (4px rhythm)

The Tailwind default spacing scale is already a 4px rhythm; do not extend it. Conventions:

| Spacing | Notation | Scenario |
|---|---|---|
| 4 / 8 | `p-1`/`p-2`, `gap-1`/`gap-2` | Inside controls (icon and text, badge padding) |
| 12 | `p-3`, `gap-3` | Between controls, list row spacing, card padding (compact) |
| 16 | `p-4`, `gap-4` | Standard card padding, between sections |
| 20 / 24 | `p-5`/`p-6` | Page-level whitespace, sign-in page padding |
| 32 | `p-8` | Large section separation (rare) |

### 4.2 Radius (Tailwind default scale, not redefined)

| Token | Value | Scenario |
|---|---|---|
| `rounded` | 4px | Elements inside badges, `kbd`, dots inside chips |
| `rounded-md` | 6px | Inputs, chips, small buttons, code snippet background |
| `rounded-lg` | 8px | Buttons, dropdown menus, toasts, tooltips, Controls/MiniMap |
| `rounded-xl` | 12px | Cards, node cards, modals, drawers (old node 14px converges to 12px) |
| `rounded-2xl` | 16px | Sign-in page large card |
| `rounded-full` | — | Badges, avatars, dot handles |

### 4.3 Border Widths

- Default `border` (1px): cards, inputs, tables.
- Selection/emphasis outline 1.5px: canvas nodes only (SVG/box-shadow implementation, see `shadow-node-active`).
- 2px: focus ring (`ring-2`, see §7 shared focus spec).
- Decorative thick borders of 2px+ are prohibited.

### 4.4 Shadows (5 tiers, key names kept + new modal)

Neutral shadow rgba is based on slate-900 `#0F172A` (the cool gray shadow is unchanged); the outer ring and shadow of `shadow-node-active` are based on brand orange (brand-600/brand-700), echoing the node selected state:

| Token | Value | Purpose |
|---|---|---|
| `shadow-card` | `0 1px 2px rgba(15, 23, 42, 0.05), 0 2px 8px -4px rgba(15, 23, 42, 0.08)` | Resting cards, node hover |
| `shadow-node` | `0 1px 2px rgba(15, 23, 42, 0.06), 0 4px 12px -6px rgba(15, 23, 42, 0.10)` | Canvas node default |
| `shadow-node-active` | `0 0 0 1.5px rgba(234, 88, 12, 0.55), 0 8px 24px -12px rgba(194, 65, 12, 0.35)` | Node selected/seed (includes brand-600 outer ring) |
| `shadow-float` | `0 2px 6px rgba(15, 23, 42, 0.06), 0 12px 32px -12px rgba(15, 23, 42, 0.18)` | Dropdown menus, tooltips, toasts, drawers, Controls/MiniMap |
| `shadow-modal` | `0 8px 24px rgba(15, 23, 42, 0.12), 0 24px 64px -16px rgba(15, 23, 42, 0.25)` | Modals (new emphasis level) |

### 4.5 Control Heights and Key Dimensions (compact values at density 8)

| Control | Dimension |
|---|---|
| Button sm / md | 28px (`h-7`, in canvas, in table rows) / 32px (`h-8`, default) |
| Button lg (sign-in submit, wizard primary action) | 36px (`h-9`) |
| Input | 32px (`h-8`, compact in canvas/filters) / 36px (`h-9`, form default, `.field-input` default height) |
| Top bar TopBar | 56px (`h-14`; current 68px tightened) |
| Sidebar DatasetSidebar width | 240px (current ~220 converged and unified) |
| Right detail panel width | 320px |
| Right drawer | 360px (field/change history) / 480px (AI chat, versions), two tiers |
| Modal | sm 400 / md 560 / lg 720 / xl 880px, four tiers (`max-w-*` + centered) |
| Node card | 288px fixed width (`lib/layout.ts` constants, unchanged); header 56px, field row 34px unchanged |
| Icon button hit area | ≥24px (`h-6 w-6` minimum) |

---

## 5. Motion Tokens

### 5.1 Durations and Easing

| Step | Value | Scenario |
|---|---|---|
| `duration-150` | 150ms | hover/active color, border, icon displacement (`transition-colors` default duration) |
| `duration-200` | 200ms | Dropdown menus, toast enter/exit, drawer slide-in, input focus |
| `duration-300` | 300ms | Modal entrance, panel expansion, list item fade-up (the 300ms ceiling satisfies the constraint) |

Easing: entrance/displacement uniformly uses `out-quint` = `cubic-bezier(0.22, 1, 0.36, 1)` (existing value kept, Tailwind extends `transitionTimingFunction['out-quint']`, class `ease-out-quint`); pure color transitions use the default `ease-out`. `ease-in` is prohibited (entrances feel sluggish).

### 5.2 Keyframe Decisions (all 4 kept, durations converged)

| Keyframe | Old | New | Rationale |
|---|---|---|---|
| `fade-up` | 420ms | **300ms** `out-quint` | List/panel entrance; 420ms exceeds the 300ms ceiling and is slow |
| `fade-in` | 260ms | **200ms** `ease-out` | Dropdown/menu/mask fade-in |
| `modal-in` | 260ms | **250ms** `out-quint` | Modal entrance (14px upward move + scale 0.985 kept) |
| `soft-pulse` | 1.8s infinite | **keep 1.8s** | Only two places: auxiliary flow semantics for AI suggestion edges, and skeleton pulse. Continuous animation is globally disabled under `prefers-reduced-motion` (rule already in index.css, kept) |

`dataset-card-in` (360ms) in `index.css` converges to 250ms `out-quint`; logic unchanged.

---

## 6. z-index Layer Table

Do not extend `theme.zIndex`; use Tailwind default tiers + arbitrary values. **Global layering (low → high)**:

| Layer | z value | Content |
|---|---|---|
| Canvas content | 0 (inside React Flow) | Nodes, edges, handles (seed nodes are raised by React Flow `zIndex`, not global tiers) |
| Canvas overlays | `z-20` | Controls, MiniMap, edge tooltip (`.react-flow__panel` current value 20, kept), `EdgeLabelRenderer` layer |
| Top bar | `z-30` | TopBar (sticky, current value kept) |
| Drawer | mask `z-40` / panel `z-[41]` | Right drawers (HistoryDrawer/VersionDrawer/AiAssistantDrawer) |
| Modal | mask `z-50` / panel `z-[51]` | PreviewModal, EdgeCreateModal, UserManagementModal, ConfirmDialog (modals can stack above drawers) |
| Toast | `z-[60]` | Global notifications (highest, visible in any state) |

Rule: components must not use z values outside the scale; overlays always follow "mask one level lower, panel one level higher" so a mask never covers its own panel.

---

## 7. Shared Component Specifications (cross-cutting; page documents reference these)

### 7.1 Buttons (4 variants × 5 states)

Unified skeleton: `inline-flex items-center justify-center gap-1.5 rounded-lg text-[13px] font-medium transition-colors duration-150` + variant class + size (default `h-8 px-3`). **Unified focus spec (all interactive elements)**: `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white`; on deep orange backgrounds (brand-800+) switch to `ring-white/60`.

| Variant | default | hover | active | disabled | focus |
|---|---|---|---|---|---|
| **primary** `btn-primary` | `bg-brand-700 text-white` (Clew redesign: white on brand-600 is only 3.56:1, so solid buttons move up one tier across the board) | `hover:bg-brand-800` | `active:bg-brand-900` | `disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed` (neutralized, no semi-transparent orange) | Unified focus |
| **secondary** | `border border-line-strong bg-card text-ink-soft` | `hover:border-brand-400 hover:text-brand-700` | `active:bg-brand-50` | `disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:border-line-strong` | Unified focus |
| **ghost** | `text-ink-muted` (no border, no background) | `hover:bg-subtle hover:text-ink` | `active:bg-line` | Same as secondary | Unified focus |
| **danger** | `bg-danger text-white` | `hover:bg-danger-deep` | `active:bg-danger-deep` | Same disabled as primary | Unified focus |

Complete example (primary, directly copyable):

```html
class="inline-flex h-8 items-center justify-center gap-1.5 rounded-lg bg-brand-700 px-3 text-[13px] font-medium text-white transition-colors duration-150 hover:bg-brand-800 active:bg-brand-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-600/60 focus-visible:ring-offset-1 focus-visible:ring-offset-white disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
```

Danger ghost variant (delete entry inside lists): `border border-danger/25 bg-danger-soft text-danger-deep hover:border-danger/45`. Buttons with icons: icon 14px, same color as text; icon-only buttons have a hit area ≥24×24 + `aria-label`.

### 7.2 Inputs and Label Layout

The `.field-input` component class stays in `index.css` (updated to the orange scheme, §8.2), default `h-9`; compact contexts add `h-8`.

- label: `mb-1.5 block text-[12px] font-medium text-ink-soft` (`htmlFor` required; search fields use `sr-only`).
- Input internal states (implemented by the component class): resting `border-line bg-card/60` → hover `border-line-strong` → focus `border-brand-600 bg-card + ring-2 ring-brand-600/15`; placeholder `text-ink-faint`; disabled `opacity-50 cursor-not-allowed`.
- Input with leading icon (search): icon `absolute left-3 text-ink-faint`, turning `text-brand-600` on focus-within; input `pl-9`.

### 7.3 Dropdown Select

- Native select (sidebar filters, etc.): `.field-input h-8 pr-8 appearance-none` + a 14px chevron icon on the right.
- Custom menu (user menu, role selection): container `rounded-lg border border-line bg-card py-1 shadow-float animate-fade-in` (z per the layer table); menu item `flex h-8 items-center gap-2 px-3 text-[13px] text-ink-soft hover:bg-subtle focus-visible:bg-subtle`; current item `bg-brand-50 text-brand-800 font-medium`; group heading `px-3 py-1.5 text-[11px] text-ink-faint`; divider `my-1 border-t border-line-soft`.

### 7.4 Badges

Skeleton: `inline-flex h-5 items-center gap-1 rounded-full border px-2 text-[11px] leading-none` (with a leading dot: `gap-1.5` + `h-1.5 w-1.5 rounded-full`).

**Source badge (SourceBadge, three source values + unknown fallback)**

| source | Class combination | Dot |
|---|---|---|
| imported (file import) | `border-slate-200 bg-slate-100 text-slate-700` (Clew redesign: former blue changed to neutral gray, echoing the imported graphite edge) | `bg-slate-600` |
| manual (manual confirmation) | `border-teal-200 bg-teal-50 text-teal-700` (Clew redesign: former amber changed to teal, same family as manual edges) | `bg-teal-600` |
| ai (AI suggestion) | `border-ai/25 bg-ai-soft text-ai-deep` | `bg-ai` |
| unknown fallback | `border-line bg-card/70 text-ink-muted` | `bg-ink-faint` |

**Role badges (admin/editor/viewer)**

| Role | Class combination |
|---|---|
| admin (administrator) | `border-transparent bg-brand-800 text-white` |
| editor (editor) | `border-brand-200 bg-brand-50 text-brand-800` |
| viewer (read-only) | `border-line bg-subtle text-ink-muted` |

**Status badges** (import batch status, version status) reuse the semantic colors: success `bg-success-soft text-success-deep`, failure `bg-danger-soft text-danger-deep`, in progress `bg-info-soft text-info-deep`, pending confirmation `bg-warning-soft text-warning-deep` (all `border-transparent`).

### 7.5 Chips

Filter conditions, AI tool names, locator anchors: `inline-flex h-6 items-center gap-1 rounded-md border border-line bg-card px-2 font-mono text-[11px] text-ink-muted`; a removable chip appends a `h-4 w-4` close icon button (`hover:bg-subtle`); an active chip is `border-brand-300 bg-brand-50 text-brand-800`.

### 7.6 Modals

- Mask: `fixed inset-0 z-50 bg-slate-900/40 animate-fade-in` (click to close; for ConfirmDialog-like dangerous actions that keep the existing rule of not closing on mask click, remove onClick).
- Panel: `relative z-[51] mx-auto w-full rounded-xl border border-line bg-card shadow-modal animate-modal-in` + size tiers (sm `max-w-[400px]` / md `max-w-[560px]` / lg `max-w-[720px]` / xl `max-w-[880px]`), `max-h-[85vh] flex flex-col`.
- Structure: header `flex h-12 shrink-0 items-center justify-between border-b border-line-soft px-4` (title `text-[14px] font-semibold text-ink` + close icon button); body `flex-1 overflow-y-auto px-4 py-4`; footer `flex h-12 shrink-0 items-center justify-end gap-2 border-t border-line-soft px-4` (primary action on the right, secondary action on the left or left of the primary).
- Behavior: Esc closes; focus moves in on open; focus restores on close (existing ConfirmDialog behavior kept).

### 7.7 Right Drawers

- Mask: `fixed inset-0 z-40 bg-slate-900/25 animate-fade-in`.
- Panel: `fixed right-0 top-0 z-[41] h-full bg-card border-l border-line shadow-float flex flex-col`; width tiers `w-[360px]` (detail/history) / `w-[480px]` (AI chat/versions); slide-in 200ms `out-quint` (transform translateX).
- Structure: header `flex h-12 items-center justify-between border-b border-line-soft px-4` (title `text-[14px] font-semibold` + close button); body `flex-1 overflow-y-auto`; AI chat bottom input area `border-t border-line-soft p-3`.
- Esc closes; a modal can open on top of a drawer (guaranteed by the layer table).

### 7.8 Toast

`fixed right-4 bottom-4 z-[60] flex h-10 items-center gap-2 rounded-lg border px-3.5 text-[13px] shadow-float animate-fade-up`; three states: success `border-success/25 bg-success-soft text-success-deep`, error `border-danger/25 bg-danger-soft text-danger-deep`, info `border-info/25 bg-info-soft text-info-deep` (info keeps blue semantics and does not follow the brand recolor); left status icon 14px, same color as text; auto-dismiss 4.2s (current value kept); `role="alert"/"status"` kept.

### 7.9 Empty States

Centered column layout: icon 24px `text-ink-faint` → main copy `text-[13px] font-medium text-ink-soft` → description `text-xs text-ink-muted` → (optional) secondary button. Container `flex flex-col items-center justify-center gap-2 py-12`.

### 7.10 Loading States

- Spinner: `h-4 w-4 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600` (small: `h-3.5 w-3.5 border-[1.5px]`; on dark backgrounds `border-white/40 border-t-white`).
- Skeleton: `animate-soft-pulse rounded-md bg-subtle` (dataset list loading, replacing the current implementation).
- Top bar subgraph loading spinner: `h-2.5 w-2.5 border-[1.5px] border-brand-300 border-t-brand-700`.

### 7.11 Icon Specifications

- The 42 built-in SVG icons in `Icon.tsx` are **kept as-is** (no icon library introduced); `stroke-width` is uniformly **1.5** (lucide style, consistent with the current implementation).
- Three size tiers: 12 (inline micro icons) / 14 (buttons, menus, badges; default) / 16 (toolbars, empty states). Decorative icons use `aria-hidden`; semantic icons keep the existing `aria-label` convention.
- Color is always `currentColor` (inherited from text color); icons must not be given out-of-scale colors individually.

### 7.12 Internationalization and Language Switching (zh/EN, new in 2026-10)

- **Approach**: in-house lightweight i18n (`src/i18n/`: `I18nProvider` + `useI18n()` + `t(key, params)`, `{var}` interpolation), no third-party library. Default zh, no automatic browser language detection; the preference persists in `localStorage['clew.locale']` and takes effect immediately on switch.
- **Dictionaries**: modularized per component in `src/i18n/dicts/<ns>.ts` (zh entries `as const` serve as the type baseline; en is compile-time forced to matching keys via `Record<XxxKey, string>`); `zh.ts`/`en.ts` only aggregate; shared entries are centralized in `dicts/common.ts` (common.*); bare copy in components is prohibited.
- **Switch control LanguageToggle**: two-segment `中 | EN`; container `flex h-7 items-center rounded-lg border border-line-strong bg-card p-0.5`, segment button `flex h-6 items-center rounded-md px-1.5 font-mono text-[11px] font-medium`, selected `bg-subtle text-ink`, unselected `text-ink-faint hover:text-ink-soft`, `aria-pressed`; mount positions: in the TopBar between the jump-count group and the user area, and at the top-right of the sign-in page card (`absolute right-4 top-4 z-20`).
- **Global items that follow locale**: `<html lang>` (zh-CN/en), `document.title` (`Clew · 字段级血缘` / `Clew · Field-level Data Lineage`), and `Intl.NumberFormat` in `formatCount`.
- **Items not translated**: backend error messages and AI answers (backend copy; Accept-Language following is out of scope for this cycle), business data (dataset/field names), source values and format words (csv/xlsx/json, sheet names), code comments.

---

## 8. Target Tailwind Configuration Code and Key index.css Sections

### 8.1 Complete `tailwind.config.cjs` (theme.extend, paste-ready)

```js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        /* Surfaces */
        page: '#F8FAFC',      // Page/canvas background (slate-50)
        card: '#FFFFFF',      // Card/panel/modal surface
        subtle: '#F1F5F9',    // Secondary surface: table header, code background, hover row (slate-100)
        /* Text */
        ink: {
          DEFAULT: '#0F172A', // Primary text (slate-900)
          soft: '#334155',    // Secondary text (slate-700)
          muted: '#475569',   // Supporting text (slate-600)
          faint: '#64748B',   // Placeholder/disabled supporting (slate-500)
        },
        /* Borders */
        line: {
          DEFAULT: '#E2E8F0', // Default border (slate-200)
          strong: '#CBD5E1',  // Strong border/hover (slate-300)
          soft: '#F1F5F9',    // Weak divider (= subtle)
        },
        /* Brand primary (Clew yarn-ball orange; anchors: 600=#EA580C, 700=#C2410C; with slate neutrals forms cool gray + warm orange) */
        brand: {
          50: '#FFF7ED',
          100: '#FFEDD5',
          200: '#FED7AA',
          300: '#FDBA74',
          400: '#FB923C',
          500: '#F97316',
          600: '#EA580C',
          700: '#C2410C',
          800: '#9A3412',
          900: '#7C2D12',
        },
        /* Semantic colors (DEFAULT=icons/white-background text/solid background, soft=light background, deep=body text on soft background)
           Since the Clew redesign warning uses deep amber (one step darker than brand orange) to avoid on-screen confusion with brand orange */
        success: { DEFAULT: '#15803D', soft: '#F0FDF4', deep: '#166534' },
        warning: { DEFAULT: '#B45309', soft: '#FFFBEB', deep: '#92400E' },
        danger: { DEFAULT: '#DC2626', soft: '#FEF2F2', deep: '#B91C1C' },
        info: { DEFAULT: '#2563EB', soft: '#EFF6FF', deep: '#1E40AF' },
        /* AI functional color (indigo, distinct from brand orange; body text on soft backgrounds uses deep) */
        ai: { DEFAULT: '#4F46E5', soft: '#EEF2FF', deep: '#3730A3' },
        /* Lineage edge source colors (for getEdgeVisual forms only, SVG stroke; kept in sync with lib/edgeColors.ts) */
        lineage: {
          imported: '#475569',        // imported field-level (solid 1.55)
          'imported-weak': '#64748B', // imported table-level (dashed 1.4)
          manual: '#0D9488',          // Manually confirmed (teal-600; former amber yields to brand orange)
          ai: '#4F46E5',              // AI suggestion (dashed + flow)
          derived: '#94A3B8',         // View-derived: inferred line for same-name field matching at both ends of table-level lineage (dotted 2 4)
          focus: '#EA580C',           // Field tracking highlight (= brand orange, "light the clue"; danger red only for deletion/validation failure)
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
          '0 0 0 1.5px rgba(234, 88, 12, 0.55), 0 8px 24px -12px rgba(194, 65, 12, 0.35)',
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
      },
      animation: {
        'fade-up': 'fade-up 300ms cubic-bezier(0.22, 1, 0.36, 1) both',
        'fade-in': 'fade-in 200ms ease-out both',
        'modal-in': 'modal-in 250ms cubic-bezier(0.22, 1, 0.36, 1) both',
        'soft-pulse': 'soft-pulse 1.8s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
```

### 8.2 Key Sections to Change in `src/index.css`

**(1) Font @import (remove the two serif families)**

```css
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Noto+Sans+SC:wght@400;500;600;700&display=swap');
```

**(2) body base styles (base layer)**

```css
body {
  @apply bg-page font-sans text-ink antialiased;
  margin: 0;
  font-feature-settings: 'kern' 1;
  text-rendering: optimizeLegibility;
}
```

**(3) Selection color and scrollbar (orange replacement)**

```css
::selection {
  background: #ffedd5;  /* brand-100 */
  color: #7c2d12;       /* brand-900 */
}

* {
  scrollbar-width: thin;
  scrollbar-color: #cbd5e1 transparent;  /* line-strong */
}
/* ::-webkit-scrollbar-thumb background #cbd5e1, hover #94a3b8; other rules (7px/radius) unchanged */
```

**(4) `.field-input` (component layer, blue-scheme focus)**

```css
.field-input {
  @apply w-full rounded-md border border-line bg-card/60 px-3 text-[13px] text-ink outline-none transition-all duration-150 placeholder:text-ink-faint;
  height: 36px; /* Compact contexts override with h-8 at the page level */
}
.field-input:hover:not(:disabled) { border-color: #cbd5e1; }
.field-input:focus {
  border-color: #ea580c;   /* brand-600 */
  background: #ffffff;
  box-shadow: 0 0 0 2px rgba(234, 88, 12, 0.15);
}
.field-input:disabled { cursor: not-allowed; opacity: 0.5; }
```

(The old `rounded-xl` converges to `rounded-md`, consistent with §7.2; the shadow converges from a 3px ring to 2px.)

**(5) React Flow canvas section (`.lineage-flow` and below)**—structure kept, color values replaced:

- `.lineage-flow` background: remove the beige radial gradient, use `background: #f8fafc;` + the dot grid provided by the container classes `bg-dot-grid bg-grid-24` (add the classes on the canvas component).
- `.react-flow__node-dataset.selected .dataset-card`: selection shadow changed to `0 0 0 1.5px rgba(234,88,12,.55), 0 8px 24px -12px rgba(194,65,12,.35)` (= `shadow-node-active`).
- `.dataset-card` entrance animation `dataset-card-in` duration 360ms→250ms.
- `.react-flow__node-dataset:focus-visible .dataset-card`: outline changed to `2px solid rgba(234, 88, 12, 0.65)`.
- `.table-handle`: border `#cbd5e1`, background `#ffffff`, outer ring `0 0 0 2px rgba(248,250,252,.9)`; hover `border-color:#c2410c; background:#ffedd5; box-shadow:0 0 0 3px rgba(234,88,12,.15)`.
- `.field-handle`: border `#cbd5e1`, background `#f8fafc`, opacity 0.55; active `border-color:#ea580c; background:#fff7ed` + brand ring; tracked state `.field-handle-traced` same values with opacity 1.
- `.lineage-controls` / `.lineage-minimap`: background `#ffffff`, border `#e2e8f0`, radius `8px`, `shadow-float` values; button hover `background:#f8fafc; color:#c2410c`.
- The `@media (prefers-reduced-motion: reduce)` rule is **kept as-is** (disabling all animations/transitions).

---

## 9. Old → New Token Mapping (perform the global replacement accordingly during development)

### 9.1 Colors

> This table records the migration mapping of the **first hi-fi version** (old prototype pine green family → the then-blue family); the "new value" in each row is the historical blue-era color, for traceability only. The **2026-10 Clew redesign** has already executed a second migration across the codebase: `blue-*` → `brand-*` (orange values in §2.1), `lineage-manual` → teal, `lineage-focus` → brand orange, warning deepened; blue tiers no longer exist in the current code, and new code always references the brand tiers in §2.1.

| Old token (old value) | New token (new value) | Note |
|---|---|---|
| `bg-canvas` (#f3f0e7) | `bg-page` (#F8FAFC) | Page/canvas background |
| `bg-surface` (#fffdf8) | `bg-card` (#FFFFFF) | Card surface |
| — (none) | `bg-subtle` (#F1F5F9) | New secondary surface; old hard-coded beige backgrounds such as `bg-[#f8f5ed]`, `bg-[#fbf9f3]` all point to this tier |
| `text-ink` (#1b2a25) | `text-ink` (#0F172A) | Same name, new value |
| `text-ink-soft` (#3b4d45) | `text-ink-soft` (#334155) | Same name, new value |
| `text-ink-muted` (#506159) | `text-ink-muted` (#475569) | Same name, new value |
| `text-ink-faint` (#66746d) | `text-ink-faint` (#64748B) | Same name, new value |
| `border-line` (#dcd6c9) | `border-line` (#E2E8F0) | Same name, new value |
| `border-line-strong` (#c9c2b3) | `border-line-strong` (#CBD5E1) | Same name, new value |
| `border-line-soft` (#ece8de) | `border-line-soft` (#F1F5F9) | Same name, new value |
| `pine-50` (#eef7f2) | `brand-50` (#EFF6FF) | Hover background/light background |
| `pine-100` (#d7ece1) | `brand-100` (#DBEAFE) | Light outline/badge border |
| `pine-200` (#b3d9c7) | `brand-200` (#BFDBFE) | Seed header border |
| `pine-300` (#83bfa6) | `brand-300` (#93C5FD) | Graphic accents |
| `pine-400` (#519f83) | `brand-400` (#60A5FA) | Secondary graphics |
| `pine-500` (#2f8268) | `brand-500` (#3B82F6) | ring/selection outline (graphics) |
| `pine-600` (#1f6753) | `brand-600` (#2563EB) | Primary button/link text |
| `pine-700` (#1a5344) | `brand-700` (#1D4ED8) | Primary button hover |
| `pine-800` (#174237) | `brand-800` (#1E40AF) | Dark background/badge deep text |
| `pine-900` (#13362e) | `brand-900` (#1E3A8A) | Sign-in dark panel |
| `ember` (DEFAULT #b9552f / soft #f8e9df / deep #8d3e20) | `danger` (#DC2626 / #FEF2F2 / #B91C1C) | Merged into danger |
| `rosewood` (#9b3a43 / #f8e8e9 / #742b32) | `danger` (same as above) | Merged with ember (same error/danger semantics) |
| `ochre` (#a36b11 / #fbf1d9 / #78500c) | `warning` (#D97706 / #FFFBEB / #B45309) | Warning/manual edges |
| `ai` (#2f64d8 / #eaf0ff / #214aa3) | `ai` (#4F46E5 / #EEF2FF / #3730A3) | Same name, new value (indigo-ized, §2.4) |
| Edge color `#2f64d8` (getEdgeVisual ai) | `lineage-ai` (#4F46E5) | Goes through constants |
| Edge color `#a36b11` (manual) | `lineage-manual` (#D97706) | Goes through constants |
| Edge color `#52645c` (imported field-level) | `lineage-imported` (#475569) | Goes through constants |
| Edge color `#8b958f` (imported table-level) | `lineage-imported-weak` (#64748B) | Goes through constants |

> Usage counts (to estimate replacement scope): `text-ink-faint` 195, `border-line` 132, `bg-surface` 110, rosewood 104, pine-* ~260 total, ember 31, ochre 24, `font-display` 12. Because ink/line are same-name value changes, most files need **zero changes**; mechanical replacements concentrate on three groups—pine→blue (first version), rosewood/ember→danger, ochre→warning; the Clew redesign then performed one more group, blue→brand.

### 9.2 Typography / Shadows / Backgrounds / Motion

| Old | New | Note |
|---|---|---|
| `font-display` (Newsreader / Song-style serif) | `font-sans` + font-size/weight adjustments (§3.1) | Serif family removed; sign-in page headline re-laid-out per the 01 page document |
| `shadow-card` | `shadow-card` (new value) | Same name, new value |
| `shadow-float` | `shadow-float` (new value) | Same name, new value |
| `shadow-node` / `shadow-node-active` | Same names (new values) | Same name, new value; `shadow-modal` added |
| `bg-fine-grid bg-grid-28` | `bg-dot-grid bg-grid-24` | Square grid → dot grid |
| `animate-fade-up` (420ms) | `animate-fade-up` (300ms) | Same name, duration change |
| `animate-fade-in` (260ms) | `animate-fade-in` (200ms) | Same name, duration change |
| `animate-modal-in` (260ms) | `animate-modal-in` (250ms) | Same name, duration change |
| `animate-soft-pulse` (1.8s) | Unchanged | Kept |
| `ease` hard-coded cubic-bezier(0.22,1,0.36,1) | `ease-out-quint` | New easing token |
| index.css: `::selection` #cce4d8/#13362e | #DBEAFE/#1E3A8A | |
| index.css: scrollbar #c9c2b3/#a9a192 | #CBD5E1 / hover #94A3B8 | |
| index.css: `.lineage-flow` beige gradient background | #F8FAFC + `bg-dot-grid bg-grid-24` | |
| index.css: `dataset-card-in` 360ms | 250ms | |
| Hard-coded decorative colors (sign-in page `#203f36`, `#8fb0a3`, `#173b31` and other deep green family) | Sign-in page dark panel unified to the `brand-900` family | Execute per the 01 page document |
| `rounded-[14px]` (node) | `rounded-xl` (12px) | |
| TopBar `min-h-[68px]` | `h-14` (56px) | |
| Fragmented font sizes 7.5/8/8.5/9/9.5/10.5px | `text-[11px]` / `text-xs` (12px) | §3.2 convergence |
| Sign-in page 46/55px display headline | `text-[28px]` / `text-2xl` sans | §3.2 exception |

---

## 10. Accessibility Checklist (Web desktop applicable items, Pass/Fail each before delivery)

1. **Text contrast**: all body-text combinations ≥4.5:1 (per the §2.6 verification table); soft-background badge/notice body text must use the deep tier; `ink-faint` must not appear as body text on subtle backgrounds. Spot-check ≥3 actually rendered combinations per page with a color picker.
2. **Graphic contrast**: lineage edges, focus ring, selection outline, icons ≥3:1 (§2.6 graphics table). Logged known item: input resting-state border 1.23:1 (industry-common trade-off, compensated by placeholder + focus state)—keep it logged; do not change the design.
3. **Visible focus**: all interactive elements (buttons/inputs/menu items/nodes/edges/close buttons) have `:focus-visible` styles (unified ring spec §7.1) and are not clipped by `overflow`; the keyboard-focus outline on canvas nodes (2px brand-600/65 + 3px offset) is reachable. Tab traversal through the sign-in page, top bar, sidebar, and canvas tool panel has no focus loss.
4. **prefers-reduced-motion**: when the system enables reduced motion, `fade-*`/`modal-in`/`soft-pulse`/AI edge flow/node entrance all become static (covered by the global rule in `index.css`; do not bypass that rule when changing animations).
5. **Keyboard accessible**: search box focused by the `/` shortcut (kept); modal Esc close + focus trap + focus restoration (generalize ConfirmDialog behavior to all modals); drawer Esc close; `aria-expanded`/`aria-haspopup`/`role` follow the existing component implementation and are not lost due to the visual redesign.
6. **Color is not the sole encoding**: lineage sources differ by dashed line style + badge text in addition to color; AI edges additionally have flow animation; dangerous actions have textual descriptions.
7. **Hit targets**: icon button hit area ≥24×24; top bar jump-count buttons ≥25×24.
8. **Transition duration**: all interaction motion 150–300ms (§5.1); no state transition exceeds 300ms.

---

## 11. Page Document Index (placeholder; other agents fill in links after creation)

| Document | Screens covered (6 lo-fi screens) |
|---|---|
| `01_login.md` | Sign-in screen (LoginPage: two-column card, dark blue panel, form) |
| `02_lineage-canvas.md` | Lineage canvas (TopBar, DatasetSidebar, LineageCanvas, DatasetNode/GroupNode/LineageEdge, DetailPanel/EdgeDetailPanel) |
| `03_source-preview.md` | Source file preview (PreviewModal: CSV/XLSX/JSON three forms) |
| `04_import-wizard.md` | Import wizard (upload source file + import checklist; frontend not yet implemented, pure design spec) |
| `05_ai-chat-and-user-management.md` | AI chat (AiAssistantDrawer) + user management (UserManagementModal) |
| `06_versions-and-change-history.md` | Version drawer (VersionDrawer) + change history (HistoryDrawer) + secondary confirmation (ConfirmDialog) |

> Page document writing convention: when referencing tokens from this document, write the token name (e.g. `brand-600`, `shadow-float`) and do not repeat the values; reference component specs directly by §7 subsection number; any new page-level style must first be written back into this document before use.

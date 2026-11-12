---
name: Fiscal Precision Platform
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#434655'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#575e70'
  on-secondary: '#ffffff'
  secondary-container: '#dbe2f8'
  on-secondary-container: '#5d6476'
  tertiary: '#006242'
  on-tertiary: '#ffffff'
  tertiary-container: '#007d55'
  on-tertiary-container: '#bdffdb'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#dbe2f8'
  secondary-fixed-dim: '#bfc6db'
  on-secondary-fixed: '#141c2b'
  on-secondary-fixed-variant: '#3f4758'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 30px
    fontWeight: '600'
    lineHeight: 38px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 22px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  label-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.04em
  data-tabular:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: -0.01em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-mobile: 0.75rem
  margin: 1.75rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.875rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

This design system establishes an exacting, low-cognitive-load digital workspace engineered for Mexican certified public accountants (CPAs), fiscal auditors, and corporate tax directors. Operating at the intersection of stringent fiscal compliance (SAT, CFDI 4.0, DIOT, e.firma validation) and high-throughput enterprise productivity, the UI balances structural rigor with understated elegance.

The design philosophy combines the focused utility of Linear, the structural composure of Stripe Dashboard, and the spatial clarity of Notion:
- **Calm, High-Density Ergonomics:** Eliminates visual static. Accountants interact with hundreds of ledger lines, RFC validations, and tax schedules for 8+ hours continuously; surfaces reduce eye fatigue through soft, tinted whites and balanced contrast.
- **Architectural Utility:** Crisp 1px structural framing, zero decorative noise, strict tabular alignment, and disciplined visual hierarchies that elevate confidence in mission-critical fiscal calculations.
- **Contextual Integrity:** Tailored natively to Mexican fiscal workflows, featuring distinct validation mechanics for CFDI cancellation statuses, e.firma certificate expiration thresholds, and immediate SAT opinion of compliance indicators (*32-D Positiva/Negativa*).

## Colors

The palette employs a dual-surface visual architecture: an anchoring, obsidian navy sidebar framing a soft, high-legibility workspace canvas.

### Core Application Roles
- **Canvas Base (`#F4F7FB`):** A cool, tinted neutral base that prevents glare on high-resolution displays.
- **Surface Elevation (`#FFFFFF`):** High-purity white reserved for data containers, analytical cards, fiscal forms, and tabular matrices.
- **Brand Action (`#2563EB`):** High-clarity cobalt blue for focal primary actions, CFDI generation triggers, and active navigation nodes.
- **Sidebar Anchor (`#101827`):** Deep navy obsidian creating persistent architectural anchoring, visually separating contextual navigation from active computational canvases.
- **Borders & Dividers (`#E2E8F0`):** Hairline, low-contrast structural partitions.

### Fiscal Status & System Signals
- **Emerald Success (`#10B981`):** Indicates valid CFDI stamping (Timbrado SAT exitoso), active CSD certificates, and "Opinión de Cumplimiento 32-D Positiva".
- **Amber Caution (`#F59E0B`):** Warns of upcoming e.firma / CSD expiration (<30 days), pending CFDI cancellation acceptances, or provisional SAT reconciliation mismatches.
- **Crimson Destructive (`#EF4444`):** Indicates EFOS (Empresas que Facturan Operaciones Simuladas) alerts under Article 69-B, failed XML validation schemas, invalid RFC check digits, or revoked certificates.
- **Text Primary (`#0F172A`) & Text Muted (`#64748B`):** Precise dual-tier text hierarchy ensuring AAA WCAG compliance across analytical ledgers.

## Typography

Inter serves as the unified typographic foundation across all viewports. Its optical balance, neutral tone, and robust OpenType tabular features make it the optimal engine for dense fiscal reporting.

### Micro-Typography & Tabular Numerals
- **Tabular Figures (`tnum`, `cv05`):** All financial tables, currency balance sheets, CFDI totals, and tax sums MUST enforce `font-feature-settings: "tnum" 1, "cv05" 1`. This aligns decimal points and comma separators vertically across rows without jitter.
- **Monospace Micro-Identifiers:** For 12-13 character RFC strings, 36-character UUID fiscal folios, and CSD serial numbers, maintain standard weight with reduced size (`12px`) and tracking (`-0.005em`) to preserve column compactability.
- **Labels & Tax Types:** `label-sm` applies uppercase transformation with `0.04em` tracking strictly for metadata chips (e.g., `IVA TRASLADADO 16%`, `ISR RETENIDO`, `PUE`, `PPD`).

## Layout & Spacing

The system implements a persistent split-shell grid. Navigation lives in a fixed left drawer, while the active data workspace behaves as a responsive, fluid container bound by rigorous structural gutters.

### Layout Mechanics
- **Primary Persistent Rail / Sidebar:** 260px fixed width on desktop (`>= 1280px`), collapsible to 64px icon-rail on medium viewports (`1024px - 1279px`), hidden inside an off-canvas drawer on mobile (`< 1024px`).
- **Workspace Canvas:** Fluid width utilizing an 8pt baseline rhythm with 4pt micro-increments (`space-xs`, `space-sm`) for tabular alignment and compact forms.
- **Data Densities:**
  - *Standard Mode:* 44px table rows and standard field heights for high-level fiscal overview dashboards.
  - *Dense Mode (Accounting Workstation):* 32px table rows with 8px vertical cell padding for mass XML ledger reconciliations and DIOT imports.

## Elevation & Depth

Visual depth is achieved through structural layering and soft ambient diffusions rather than heavy artificial drop shadows.

- **Level 0 (App Canvas):** `#F4F7FB` background canvas, fully flat.
- **Level 1 (Card & Module Foundation):** `#FFFFFF` surfaces wrapped in a crisp 1px border (`#E2E8F0`) with a faint ambient contact shadow: `box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.04), 0 1px 2px -1px rgba(15, 23, 42, 0.02)`.
- **Level 2 (Popovers, Select Menus, Filter Drawers):** Elevated above the surface with clean delineation: `box-shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.07), 0 2px 4px -2px rgba(15, 23, 42, 0.05)`.
- **Level 3 (Modals & Critical Fiscal Dialogs):** Stamp authorization overlays (e.g., signing with e.firma `.cer`/`.key`) feature elevated focus: `box-shadow: 0 20px 25px -5px rgba(15, 23, 42, 0.1), 0 8px 10px -6px rgba(15, 23, 42, 0.04)` over a dark `#0F172A` backdrop tinted at 40% opacity with 2px backdrop blur.

## Shapes

The design system standardizes on clean, subtle geometric curvature (Rounded level 2) to maintain a crisp, enterprise-grade feel without appearing toy-like or sterile.

- **Inputs, Buttons, and Small Chips:** 6px to 8px border radius (`rounded-md` / base level) for balanced tactile precision.
- **Cards, Modals, and Main Data Tables:** 12px to 16px corner radius (`rounded-lg` / `rounded-xl`) to neatly frame structural borders against the soft canvas background.
- **Strictly Square Geometry:** Data grid cells, fiscal timeline segments, and horizontal code/XML previewers retain 0px interior radiuses to ensure uninterrupted alignment.

## Components

All icons are sourced exclusively from Lucide with a disciplined 1.5px stroke width, matching the hairline clarity of form borders and tabular dividers.

### Buttons & Interactive Triggers
- **Primary ("Timbrar", "Descargar XML/PDF", "Guardar"):** Solid `#2563EB`, text `#FFFFFF`, 8px radius, subtle hover shift to `#1D4ED8`. Active state shifts to `#1E40AF`.
- **Secondary / Neutral:** `#FFFFFF` background, 1px border `#E2E8F0`, text `#0F172A`. Hover transitions background to `#F8FAFC` and border to `#CBD5E1`.
- **Destructive ("Cancelar CFDI"):** Light red surface (`#FEF2F2`), border `#FCA5A5`, text `#DC2626`. Confirmatory state shifts to solid `#EF4444` with white text.

### Form Inputs & Fiscal Keypads
- **RFC & UUID Text Fields:** `#FFFFFF` background, 1px border `#E2E8F0`, 8px padding (`0.5rem 0.75rem`). Focus state utilizes `#2563EB` border with a 3px ring of `rgba(37, 99, 235, 0.12)`.
- **Currency & Decimal Fields:** Right-aligned text, prepended with a static, non-editable `$ (MXN)` prefix tag in `#64748B`. Tabular figures enforced.

### Chips & Tax Badges
- **Status Indicators (Opinión de Cumplimiento / CFDI Status):** Micro-chips (20px height, 8px horizontal padding) using saturated text on desaturated tinted fills:
  - *Vigente / Positiva:* Green tint (`#ECFDF5`), border `#A7F3D0`, text `#065F46`.
  - *Cancelado:* Slate tint (`#F1F5F9`), border `#CBD5E1`, text `#475569`.
  - *En Proceso de Cancelación:* Amber tint (`#FFFBEB`), border `#FDE68A`, text `#92400E`.
  - *EFOS / No Localizado:* Red tint (`#FEF2F2`), border `#FECACA`, text `#991B1B`.

### Ledger Data Tables
- Header cells: `#F8FAFC` fill, `#64748B` uppercase micro-text, 1px bottom border `#E2E8F0`.
- Data rows: `#FFFFFF` base, alternating hover highlight `#F8FAFC`. Active selected row: `#EFF6FF` with `#2563EB` 2px left border accent.

### Fiscal File Uploaders (e.firma / CSD)
Dual-dropzone cards for paired cryptographic assets (`.cer` certificate + `.key` private key) featuring dashed 1.5px borders (`#CBD5E1`), drag-over activation in `#2563EB`, and password input lock indicators.
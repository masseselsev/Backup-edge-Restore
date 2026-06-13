# Design Spec: Multilingual Layout & Font Scaling

## Goal
Improve the visual appearance and layout stability of the application when switched to non-English languages (Russian and Ukrainian) across all resolutions and device states. Ensure font metrics are consistent and text wrapping/truncation behaves dynamically instead of overflowing.

---

## 1. Typography & Global Styles

### Inter Font Integration
- Integrate Google Fonts' **Inter** font stylesheet in `frontend/index.html`.
- Inter has native, high-quality, and modern Cyrillic glyphs with identical spacing and heights to Latin characters.
- Update `frontend/src/index.css` to ensure `'Inter'` is first in the font-family declaration list.

### Global CSS Text Rules
- Implement standard text scaling/smoothing rules in `frontend/src/index.css`:
  - Enforce subpixel antialiasing.
  - Set relative line heights (`leading-normal` or `leading-relaxed`) to prevent Cyrillic ascenders and descenders from clipping.
  - Apply custom font-feature-settings on text buttons, labels, and links to optimize character kerning.

---

## 2. Navigation Header Adaptation

### Header Tabs (`frontend/src/App.tsx`)
- Allow navigation links to wrap/adjust on narrow displays using `flex-wrap` and adaptive `gap-x-1 sm:gap-x-2`.
- Remove fixed button/tab widths and let them expand depending on text length using padding (`px-3 py-1.5`).
- Ensure Kiosk status indicators and logout/exit buttons use `flex-shrink-0` to prevent them from compressing when navigation labels are long.

---

## 3. Component Layout Changes

### Fleet Tab Node Cards (`frontend/src/components/FleetTab.tsx`)
- Action buttons layout: Convert node action buttons (Backup, Prepare, Logs, Provision) to a flexible `flex flex-wrap gap-2` layout inside cards.
- Add `flex-1 min-w-[100px] text-center justify-center` to buttons so that they expand dynamically without causing text clipping or overflowing the card edges.
- Enforce `break-all` on hostname labels to prevent long hostnames from overflowing card borders.

### Settings Tab Layout (`frontend/src/components/SettingsTab.tsx`)
- Form settings grid: Redesign input fields layout from side-by-side labels to top-to-bottom layout (`grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4`).
- Move all input labels to be stacked directly above their corresponding inputs, which decouples label translation lengths from field input width.
- Ensure language and timezone select elements use `w-full max-w-full` behavior.

---

## 4. Translation Key Streamlining (`frontend/src/i18n/translations.ts`)

- Shorten and optimize translation lengths for Russian and Ukrainian keys to match their English counterparts:
  - `tabClientIso` (RU: "Создание Live-USB" -> "Live-USB", UK: "Створення Live-USB" -> "Live-USB").
  - `tabKiosk` (RU: "Клиент-киоск" -> "Киоск", UK: "Клієнт-кіоск" -> "Кіоск").
  - `backup` (RU: "Резервное копирование" -> "Копия", UK: "Резервне копіювання" -> "Копія").
  - `globalExclusionsLabel` (RU: "Исключения файлов (через запятую)" -> "Исключения (через запятую)", UK: "Винятки файлів (через кому)" -> "Винятки (через кому)").

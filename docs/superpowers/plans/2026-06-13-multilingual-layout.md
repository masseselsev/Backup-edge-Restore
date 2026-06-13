# Multilingual Layout & Font Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve layout stability, responsive text wrapping, and typography consistency on English, Russian, and Ukrainian languages across all key dashboard views.

**Architecture:** Integrate Google Fonts' Inter font stylesheet globally. Move forms to stacked layouts and action buttons to flex-wrapping flows with automatic width sizing. Shorten long translations to prevent overflows.

**Tech Stack:** React, TypeScript, Tailwind CSS, Google Fonts API.

---

## Files to Modify

1. **Modify:** `frontend/index.html` — Add Google Fonts Inter stylesheet link tags.
2. **Modify:** `frontend/src/index.css` — Update global font-family rules and text features.
3. **Modify:** `frontend/src/App.tsx` — Make header navigation tabs responsive to wrapping.
4. **Modify:** `frontend/src/components/FleetTab.tsx` — Make node card action buttons wrap dynamically.
5. **Modify:** `frontend/src/components/SettingsTab.tsx` — Re-layout settings form inputs from side-by-side to top-stacked labels.
6. **Modify:** `frontend/src/i18n/translations.ts` — Streamline long RU/UK text translations.

---

### Task 1: Typography & Font Integration

**Files:**
- Modify: `frontend/index.html`
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Add Google Fonts Inter preconnect and stylesheet link tags to index.html**
  
  Modify `frontend/index.html` to insert the stylesheet references inside `<head>` (before `<title>`):
  ```html
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  ```

- [ ] **Step 2: Update index.css font family and properties**
  
  Modify the `body` selector inside `frontend/src/index.css`:
  ```css
  body {
    margin: 0;
    background-color: #0b0f19;
    color: #f3f4f6;
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
  ```
  Add global text rules to the bottom of `frontend/src/index.css` for better kerning and text rendering:
  ```css
  button, a, label, span, p, h1, h2, h3, h4, h5, h6 {
    font-feature-settings: "cv02", "cv03", "cv04", "cv11";
  }
  ```

- [ ] **Step 3: Run local build to verify syntax compilation**
  
  Run: `npm run build --prefix frontend`
  Expected: Successful build with no CSS/HTML syntax errors.

---

### Task 2: Responsive Header Navigation Tabs

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Make navigation tabs row use flex-wrap and responsive gaps**
  
  Modify `frontend/src/App.tsx` to search for the navigation container (typically `flex items-center gap-4` or similar) and replace it with:
  ```tsx
  <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
  ```
  And search for the main tabs row container and update to:
  ```tsx
  <div className="flex flex-wrap items-center gap-1 bg-zinc-950/60 p-1 border border-zinc-800 rounded-xl">
  ```

- [ ] **Step 2: Remove fixed heights or rigid paddings from navigation tab buttons**
  
  Ensure tab button links use flex-grow or auto-sizing, e.g.:
  ```tsx
  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200 ...`}
  ```

- [ ] **Step 3: Ensure right side status bar doesn't wrap awkwardly**
  
  Add `flex-shrink-0` to the System Online and Exit Kiosk buttons/indicators so they stay aligned:
  ```tsx
  <div className="flex items-center gap-2 flex-shrink-0">
  ```

- [ ] **Step 4: Verify build compiles**
  
  Run: `npm run build --prefix frontend`
  Expected: Success.

---

### Task 3: Flexible Node Cards Action Buttons

**Files:**
- Modify: `frontend/src/components/FleetTab.tsx`

- [ ] **Step 1: Redesign node action buttons container**
  
  Search for the bottom action buttons row in `frontend/src/components/FleetTab.tsx` (usually styled with flex) and update it to:
  ```tsx
  <div className="flex flex-wrap gap-2 pt-3 mt-auto border-t border-zinc-800/80">
  ```

- [ ] **Step 2: Update actions buttons styling**
  
  Ensure each action button uses `flex-1 min-w-[100px] text-center justify-center` and removes rigid fixed widths (like `w-24`) so they scale:
  ```tsx
  <button
    onClick={...}
    className="flex-1 min-w-[100px] flex items-center justify-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold text-white bg-indigo-600/80 hover:bg-indigo-500 rounded-lg transition-colors"
  >
  ```

- [ ] **Step 3: Add break-all on Node hostname label**
  
  Find the hostname rendering block (usually inside `h4` or `span`) and apply word breaking classes:
  ```tsx
  <span className="font-bold text-sm text-white break-all truncate" title={node.hostname}>
  ```

- [ ] **Step 4: Verify build compiles**
  
  Run: `npm run build --prefix frontend`
  Expected: Success.

---

### Task 4: Stacked Settings Labels & Select Auto-width

**Files:**
- Modify: `frontend/src/components/SettingsTab.tsx`

- [ ] **Step 1: Replace side-by-side grid rows with stacked inputs**
  
  Search for form fields grid inside `frontend/src/components/SettingsTab.tsx` and change grid columns class to:
  ```tsx
  <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
  ```
  Ensure each label/input block stacks the label strictly on top of the input, e.g.:
  ```tsx
  <div>
    <label className="block text-xs font-semibold text-zinc-400 mb-1.5">{t('borgSshPort')}</label>
    <input
      type="number"
      ...
      className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-white text-sm focus:border-indigo-500 focus:outline-none"
    />
  </div>
  ```

- [ ] **Step 2: Update Select inputs to use full-width flexible sizing**
  
  Ensure the timezone dropdown select wrapper uses `w-full max-w-full`:
  ```tsx
  <div className="w-full max-w-full">
    <label className="block text-xs font-semibold text-zinc-400 mb-1.5">{t('systemTimezone')}</label>
    ...
  </div>
  ```

- [ ] **Step 3: Verify build compiles**
  
  Run: `npm run build --prefix frontend`
  Expected: Success.

---

### Task 5: Streamline Russian & Ukrainian Translations

**Files:**
- Modify: `frontend/src/i18n/translations.ts`

- [ ] **Step 1: Shorten navigation tab and button texts in the Russian section**
  
  Update `ru` translation properties in `frontend/src/i18n/translations.ts`:
  - `tabKiosk` to: `'Киоск'`
  - `tabClientIso` to: `'Live-USB'`
  - `backup` to: `'Копия'`
  - `globalExclusionsLabel` to: `'Исключения (через запятую)'`

- [ ] **Step 2: Shorten navigation tab and button texts in the Ukrainian section**
  
  Update `uk` translation properties in `frontend/src/i18n/translations.ts`:
  - `tabKiosk` to: `'Кіоск'`
  - `tabClientIso` to: `'Live-USB'`
  - `backup` to: `'Копія'`
  - `globalExclusionsLabel` to: `'Винятки (через кому)'`

- [ ] **Step 3: Verify build compiles**
  
  Run: `npm run build --prefix frontend`
  Expected: Success.

---

### Task 6: Rebuild and Verify

- [ ] **Step 1: Rebuild and launch the frontend Docker container**
  
  Run: `docker compose up -d --build frontend`
  Expected: Rebuilt container finishes starting successfully.

- [ ] **Step 2: Perform health check curl**
  
  Run: `curl -I http://localhost:7777`
  Expected: HTTP/1.1 200 OK.

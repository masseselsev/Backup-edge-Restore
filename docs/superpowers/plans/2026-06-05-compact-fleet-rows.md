# Compact Fleet Rows & Unified Status Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compact the layout of the Fleet table rows and integrate setup actions (Prepare/Provision) directly into the Status column badges/buttons.

**Architecture:** Frontend changes inside `FleetTab.tsx` to reduce cell padding, merge prepare/provision actions into the Status column, and simplify the Actions column.

**Tech Stack:** React, TypeScript, Tailwind CSS, Lucide icons.

---

### Task 1: Redesign and Compact Fleet Tab Rows

**Files:**
- Modify: [FleetTab.tsx](file:///home/masse/projects/Backup-edge-Restore/frontend/src/components/FleetTab.tsx)

- [ ] **Step 1: Replace getStatusBadge with renderStatusButton**
  Replace the existing `getStatusBadge` helper with an interactive `renderStatusButton(node: Node)` helper that returns buttons triggering actions based on the node status:
  - `READY`: Green button `Ready [OK]` calling `runPrepare(node.id, node.hostname)`.
  - `NEEDS_FIX`: Amber button `Needs Fix [Prepare]` calling `runPrepare(node.id, node.hostname)`.
  - `NEEDS_BOOTSTRAP`: Gray button `Provision` calling `setShowProvisionModal(node)`.
  - `OFFLINE`: Rose button `Provision` calling `setShowProvisionModal(node)`.

  *Code snippet to implement:*
  ```typescript
  const renderStatusButton = (node: Node) => {
    const baseClass = "inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border transition-colors cursor-pointer";
    switch (node.status) {
      case 'READY':
        return (
          <button
            onClick={() => runPrepare(node.id, node.hostname)}
            className={`${baseClass} bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border-emerald-500/20`}
            title="Re-run Prepare Disk"
          >
            <CheckCircle size={14} /> Ready [OK]
          </button>
        );
      case 'NEEDS_FIX':
        return (
          <button
            onClick={() => runPrepare(node.id, node.hostname)}
            className={`${baseClass} bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border-amber-500/20`}
            title="Run Prepare Disk"
          >
            <AlertTriangle size={14} /> Needs Fix [Prepare]
          </button>
        );
      case 'NEEDS_BOOTSTRAP':
        return (
          <button
            onClick={() => setShowProvisionModal(node)}
            className={`${baseClass} bg-zinc-500/10 hover:bg-zinc-500/20 text-zinc-400 border-zinc-500/20`}
            title="Provision Node"
          >
            <Gear size={14} /> Provision
          </button>
        );
      case 'OFFLINE':
      default:
        return (
          <button
            onClick={() => setShowProvisionModal(node)}
            className={`${baseClass} bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border-rose-500/20`}
            title="Provision Offline Node"
          >
            <ShieldAlert size={14} /> Provision
          </button>
        );
    }
  };
  ```

- [ ] **Step 2: Update Table Padding and Header Titles**
  Change table cell padding `px-6 py-4` to `px-4 py-2.5`. Update the status table header from `Status` to `Status / Action`.

- [ ] **Step 3: Update renderNodeRow**
  In `renderNodeRow`:
  - Update all cell `px-6 py-4` class names to `px-4 py-2.5`.
  - Render the status using `{renderStatusButton(node)}` instead of `{getStatusBadge(node.status)}`.
  - In the Actions column, remove the separate `Provision` and `Prepare Disk` buttons.
  - Retain only the `Backup` button (change text from "Backup Now" to "Backup" and make padding `px-2.5 py-1.5`) and the `Delete` (trash can) button.

- [ ] **Step 4: Verify typescript compiles and file size rule is met**
  Ensure the file line count of `FleetTab.tsx` does not exceed 500 lines. Run typescript type-checks.
  Run: `npx tsc --noEmit` inside `frontend/` directory.

- [ ] **Step 5: Run production build**
  Run: `npm run build` inside `frontend/` directory.

# Design Spec: Compact Fleet Row & Combined Status-Action Button

Make the Edge Fleet table layout and row actions more compact. Reduce visual noise and width by combining the node's status badge with its primary setup action (Prepare/Provision) and shrinking the cell padding and other action text.

## Proposed Changes

### Frontend

#### `FleetTab.tsx` ([FleetTab.tsx](file:///home/masse/projects/Backup-edge-Restore/frontend/src/components/FleetTab.tsx))
- **Interactive Status Action**:
  - Replace `getStatusBadge` with `renderStatusButton(node: Node)` returning an interactive button that performs the setup action appropriate for that state:
    - `READY` -> Green button: `Ready [OK]` (calls `runPrepare` to let users re-prepare if needed).
    - `NEEDS_FIX` -> Amber button: `Needs Fix [Prepare]` (calls `runPrepare`).
    - `NEEDS_BOOTSTRAP` -> Gray button: `Needs Provisioning` or `Provision` (opens the Provision modal).
    - `OFFLINE` -> Rose button: `Offline (Provision)` or `Provision` (opens the Provision modal).
- **Actions Column Simplification**:
  - Remove the separate "Prepare Disk" and "Provision" buttons.
  - Retain only the **Backup** button (shortened from "Backup Now") and the small **Delete** trash-bin button.
- **Row Styling & Sizing**:
  - Reduce padding of table headers (`th`) and cells (`td`) from `px-6 py-4` to `px-4 py-2.5`.
  - Reduce table text sizes where appropriate to improve fit on smaller widths.
  - Ensure the file line count stays well under the 500-line limit (currently at 454 lines).

## Verification Plan

### Automated Build Checks
- Run `npm run build` and `npx tsc --noEmit` in the `frontend` workspace to verify correct React/TypeScript compilation with no errors.

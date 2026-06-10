import React, { useState, useEffect, useRef } from 'react';
import { AlertTriangle, Server, HardDrive, RefreshCw, Play, Download } from 'lucide-react';

interface Device {
  name: string;
  size: number;
  model: string;
  rotational: boolean;
  disk_type: string;
  is_usb?: boolean;
}

interface EdgeNode {
  id: number;
  hostname: string;
  disk_type: string;
  efi_uuid: string | null;
  last_backup: string | null;
  repo_size_bytes?: number;
}

interface Snapshot {
  id: number;
  archive_name: string;
  timestamp: string;
  original_size: number;
  comment: string | null;
}

import { formatDate } from './dateUtils';
import { SearchableSelect } from './SearchableSelect';
import type { Option } from './SearchableSelect';

interface FlasherTabProps {
  onViewLogs: (taskId: string, title: string) => void;
  timezone?: string;
  restoreMode?: 'offline' | 'online';
  isKiosk?: boolean;
}

export default function FlasherTab({ onViewLogs, timezone, restoreMode = 'offline', isKiosk = false }: FlasherTabProps) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [nodes, setNodes] = useState<EdgeNode[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<number | ''>('');
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [selectedSnapshot, setSelectedSnapshot] = useState<string>('');
  const [selectedDevice, setSelectedDevice] = useState<string>('');
  
  const [scanning, setScanning] = useState(false);
  const [loadingNodes, setLoadingNodes] = useState(true);
  const [loadingSnapshots, setLoadingSnapshots] = useState(false);
  const [mismatchWarning, setMismatchWarning] = useState(false);
  const [overrideChecked, setOverrideChecked] = useState(false);
  const [keepNetworkConfigs, setKeepNetworkConfigs] = useState(true);
  const [wipeMacBindings, setWipeMacBindings] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Sync states
  const [syncing, setSyncing] = useState(false);
  const [syncTaskId, setSyncTaskId] = useState<string | null>(null);
  const [syncProgress, setSyncProgress] = useState(0);

  // Storage partition capacity state
  const [storageInfo, setStorageInfo] = useState<{
    total: number;
    used: number;
    free: number;
    path: string;
    is_mounted: boolean;
  } | null>(null);

  const handleSyncToUsb = async () => {
    if (!selectedNodeId) return;
    const node = nodes.find(n => n.id === selectedNodeId);
    if (!node) return;
    
    setSyncing(true);
    setSyncProgress(0);
    try {
      const res = await fetch(`/api/kiosk/sync/${node.hostname}`, { method: 'POST' });
      if (!res.ok) throw new Error("Failed to start sync");
      const data = await res.json();
      if (data.task_id) {
        setSyncTaskId(data.task_id);
      }
    } catch (err: any) {
      alert(`Sync failed to start: ${err.message}`);
      setSyncing(false);
    }
  };

  useEffect(() => {
    if (!syncTaskId) return;

    let intervalId: any = null;
    const pollStatus = async () => {
      try {
        const res = await fetch(`/api/tasks/${syncTaskId}`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.progress) {
          setSyncProgress(data.progress);
        }
        if (data.status === 'SUCCESS') {
          clearInterval(intervalId);
          setSyncTaskId(null);
          setSyncing(false);
          alert("Repository synced to USB successfully!");
          // Refresh lists to see cached nodes
          fetchDevices();
          fetchNodes();
          fetchStorageInfo();
        } else if (data.status === 'FAILED') {
          clearInterval(intervalId);
          setSyncTaskId(null);
          setSyncing(false);
          alert(`Sync task failed. Please check kiosk logs.`);
        }
      } catch (err) {
        console.error(err);
      }
    };

    pollStatus();
    intervalId = setInterval(pollStatus, 2000);
    return () => clearInterval(intervalId);
  }, [syncTaskId]);

  const fetchDevices = async () => {
    setScanning(true);
    try {
      const res = await fetch('/api/scanner/devices');
      const data = await res.json();
      setDevices(data);
    } catch (e) {
      console.error(e);
    } finally {
      setScanning(false);
    }
  };

  const fetchNodes = async () => {
    try {
      const res = await fetch('/api/nodes');
      const data = await res.json();
      setNodes(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingNodes(false);
    }
  };

  const fetchStorageInfo = async () => {
    if (!isKiosk) return;
    try {
      const res = await fetch('/api/kiosk/storage');
      if (res.ok) {
        const data = await res.json();
        setStorageInfo(data);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const fetchSnapshots = async (nodeId: number) => {
    setLoadingSnapshots(true);
    try {
      const res = await fetch(`/api/nodes/${nodeId}/history`);
      const data = await res.json();
      setSnapshots(data.filter((h: any) => h.status === 'SUCCESS'));
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingSnapshots(false);
    }
  };

  useEffect(() => {
    fetchDevices();
    fetchNodes();
    if (isKiosk) {
      fetchStorageInfo();
    }
  }, [isKiosk]);

  useEffect(() => {
    if (selectedNodeId) {
      fetchSnapshots(Number(selectedNodeId));
      setSelectedSnapshot('');
    } else {
      setSnapshots([]);
    }
  }, [selectedNodeId]);

  useEffect(() => {
    if (selectedNodeId && selectedDevice) {
      const node = nodes.find(n => n.id === Number(selectedNodeId));
      const device = devices.find(d => d.name === selectedDevice);
      if (node && device) {
        const isMismatch = node.disk_type !== 'UNKNOWN' && node.disk_type !== device.disk_type;
        setMismatchWarning(isMismatch);
        if (!isMismatch) {
          setOverrideChecked(false);
        }
      }
    } else {
      setMismatchWarning(false);
      setOverrideChecked(false);
    }
  }, [selectedNodeId, selectedDevice, nodes, devices]);

  const handleStartFlash = async (e: React.FormEvent) => {
    e.preventDefault();
    if (mismatchWarning && !overrideChecked) {
      setError('You must explicitly confirm you want to proceed with disk mismatch.');
      return;
    }

    setSubmitting(true);
    setError('');

    try {
      const res = await fetch('/api/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_id: Number(selectedNodeId),
          archive_name: selectedSnapshot,
          target_dev: selectedDevice,
          override_mismatch: overrideChecked,
          keep_network_configs: keepNetworkConfigs,
          wipe_mac_bindings: wipeMacBindings
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to trigger restore');

      if (data.task_id) {
        onViewLogs(data.task_id, `Restore Flashing on ${selectedDevice}`);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const getFormatSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const g = bytes / (1024 * 1024 * 1024);
    return `${g.toFixed(1)} GB`;
  };

  const selectedNode = nodes.find(n => n.id === Number(selectedNodeId));

  // Options converters
  const nodeOptions = nodes
    .filter(n => n.last_backup !== null)
    .map(n => ({
      value: n.id,
      label: n.hostname,
      sublabel: `Original Disk: ${n.disk_type}${n.efi_uuid ? '' : ' [NO EFI UUID]'}${n.repo_size_bytes !== undefined ? ` — Repo Size: ${getFormatSize(n.repo_size_bytes)}` : ''}`,
      disabled: false
    }));

  const snapshotOptions = snapshots.map(s => ({
    value: s.archive_name,
    label: s.archive_name,
    sublabel: `${formatDate(s.timestamp, timezone)} (${getFormatSize(s.original_size)})${s.comment ? ` — ${s.comment}` : ''}`,
    disabled: false
  }));

  const deviceOptions = devices.map(d => ({
    value: d.name,
    label: d.name,
    sublabel: `${d.model} (${getFormatSize(d.size)} - ${d.disk_type} ${d.rotational ? 'HDD' : 'SSD'}${d.is_usb ? ' [USB]' : ''})`,
    disabled: false
  }));

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Configuration & Trigger form */}
      <div className="lg:col-span-2 space-y-6">
        <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-2xl space-y-4">
          <div>
            <h3 className="text-lg font-bold text-white flex items-center gap-2"><Play size={18} className="text-indigo-400" /> Bare-Metal Flasher</h3>
            <p className="text-xs text-zinc-400">Configure target snapshot extraction and format target physical devices.</p>
          </div>

          <form onSubmit={handleStartFlash} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1.5">1. Select Target Node (Data Source)</label>
              <SearchableSelect
                options={nodeOptions}
                value={selectedNodeId}
                onChange={(val) => setSelectedNodeId(val)}
                placeholder="-- Choose Target Node --"
                disabled={loadingNodes}
              />
              {selectedNode && !selectedNode.efi_uuid && (
                <div className="mt-1.5 text-xs text-rose-400 flex items-center gap-1.5">
                  <AlertTriangle size={12} /> Auto-Prepare has not been run on this node. Bare-metal restore is locked.
                </div>
              )}
            </div>

            {selectedNodeId && isKiosk && restoreMode === 'online' && (
              <div className="p-4 bg-indigo-950/20 border border-indigo-900/30 rounded-xl space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h4 className="text-xs font-bold text-indigo-300 uppercase tracking-wider">Local USB Cache (Offline Restore Prep)</h4>
                    <p className="text-[10px] text-zinc-400 mt-1">
                      Download this node's full repository {selectedNode?.repo_size_bytes !== undefined ? `(${getFormatSize(selectedNode.repo_size_bytes)})` : ''} to the USB drive to allow restoring without internet.
                    </p>
                    {storageInfo && (
                      <p className="text-[10px] text-zinc-500 mt-1.5 flex items-center gap-1.5 font-semibold">
                        <HardDrive size={11} className="text-zinc-400" />
                        Storage space: <span className="text-emerald-400">{getFormatSize(storageInfo.free)} free</span> / {getFormatSize(storageInfo.total)} total
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={handleSyncToUsb}
                    disabled={syncing}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer"
                  >
                    <Download size={13} />
                    {syncing ? 'Syncing...' : 'Sync to USB'}
                  </button>
                </div>
                {syncing && (
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-[10px] font-mono text-zinc-400">
                      <span>Syncing files...</span>
                      <span>{syncProgress}%</span>
                    </div>
                    <div className="w-full bg-zinc-950 h-1.5 rounded-full overflow-hidden border border-zinc-800">
                      <div 
                        className="bg-indigo-500 h-full rounded-full transition-all duration-300"
                        style={{ width: `${syncProgress}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            )}

            {selectedNodeId && (
              <div>
                <label className="block text-xs font-semibold text-zinc-400 mb-1.5">2. Select Backup Snapshot</label>
                <SearchableSelect
                  options={snapshotOptions}
                  value={selectedSnapshot}
                  onChange={(val) => setSelectedSnapshot(val)}
                  placeholder="-- Choose Snapshot Archive --"
                  disabled={loadingSnapshots}
                />
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1.5">3. Select Target Flash Block Device</label>
              <SearchableSelect
                options={deviceOptions}
                value={selectedDevice}
                onChange={(val) => setSelectedDevice(val)}
                placeholder="-- Choose Physical Target Drive --"
                disabled={scanning}
              />
            </div>

            {/* Mismatch warnings */}
            {mismatchWarning && (
              <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-xl space-y-2">
                <div className="flex items-start gap-2.5">
                  <AlertTriangle className="text-amber-400 mt-0.5 shrink-0" size={18} />
                  <div>
                    <h4 className="text-sm font-bold text-amber-400">HARDWARE TYPE MISMATCH WARNING</h4>
                    <p className="text-xs text-zinc-300">
                      The original node was provisioned with a **{selectedNode?.disk_type}** device. 
                      You have selected a **{devices.find(d => d.name === selectedDevice)?.disk_type}** drive. 
                      Restoring to mismatched architectures could lead to boot loader PCIe driver errors.
                    </p>
                  </div>
                </div>
                <label className="flex items-center gap-2 mt-2 px-3 py-2 bg-amber-500/5 border border-amber-500/10 rounded-lg cursor-pointer">
                  <input
                    type="checkbox"
                    checked={overrideChecked}
                    onChange={(e) => setOverrideChecked(e.target.checked)}
                    className="rounded bg-zinc-950 border-zinc-800 text-indigo-600 focus:ring-0"
                  />
                  <span className="text-xs font-semibold text-amber-400">I explicitly confirm this restore mismatch and assume boot risks</span>
                </label>
              </div>
            )}

            {/* Network configuration restore options */}
            <div className="p-4 bg-zinc-950 border border-zinc-800 rounded-xl space-y-3">
              <h4 className="text-xs font-bold text-zinc-300 uppercase tracking-wider">Network Settings</h4>
              <div className="space-y-2.5">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={keepNetworkConfigs}
                    onChange={(e) => {
                      setKeepNetworkConfigs(e.target.checked);
                      if (!e.target.checked) {
                        setWipeMacBindings(true);
                      }
                    }}
                    className="mt-0.5 rounded bg-zinc-900 border-zinc-800 text-indigo-600 focus:ring-0"
                  />
                  <div className="flex flex-col">
                    <span className="text-xs font-semibold text-zinc-200">Preserve original network configurations (1-to-1)</span>
                    <span className="text-[10px] text-zinc-400">Keep static IPs and interfaces. Skip DHCP override fallback.</span>
                  </div>
                </label>

                <label className={`flex items-start gap-2.5 ${keepNetworkConfigs ? 'cursor-pointer opacity-100' : 'cursor-not-allowed opacity-50'}`}>
                  <input
                    type="checkbox"
                    checked={wipeMacBindings}
                    disabled={!keepNetworkConfigs}
                    onChange={(e) => setWipeMacBindings(e.target.checked)}
                    className="mt-0.5 rounded bg-zinc-900 border-zinc-800 text-indigo-600 focus:ring-0"
                  />
                  <div className="flex flex-col">
                    <span className="text-xs font-semibold text-zinc-200">Reset MAC address bindings (for new motherboards)</span>
                    <span className="text-[10px] text-zinc-400">Wipes persistent udev rules so interface names bind dynamically.</span>
                  </div>
                </label>
              </div>
            </div>

            {error && <div className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 p-3 rounded-lg">{error}</div>}

            <button
              type="submit"
              disabled={submitting || !selectedSnapshot || !selectedDevice || (mismatchWarning && !overrideChecked) || (selectedNode && !selectedNode.efi_uuid)}
              className="w-full py-2.5 bg-rose-600 hover:bg-rose-500 text-white rounded-lg font-bold text-sm tracking-wide shadow-lg disabled:opacity-30 disabled:hover:bg-rose-600 transition-colors"
            >
              {submitting ? 'Wiping and Flashing...' : 'START FLASHING (DANGER ZONE)'}
            </button>
          </form>
        </div>
      </div>

      {/* Local scanning status */}
      <div className="space-y-6">
        <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-2xl space-y-4">
          <div className="flex justify-between items-center">
            <h3 className="text-sm font-bold text-white flex items-center gap-2"><HardDrive size={16} /> Device Scanner</h3>
            <button
              onClick={fetchDevices}
              disabled={scanning}
              className="p-1 hover:bg-zinc-800 text-zinc-400 hover:text-white rounded transition-colors"
            >
              <RefreshCw size={14} className={scanning ? 'animate-spin' : ''} />
            </button>
          </div>
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {devices.length === 0 ? (
              <div className="text-center py-8 text-xs text-zinc-500">No external drives found. Make sure SATA/NVMe targets are plugged in.</div>
            ) : (
              devices.map(d => (
                <div key={d.name} className="p-3 bg-zinc-950 border border-zinc-800/80 rounded-xl space-y-1">
                  <div className="flex justify-between text-xs font-bold text-white">
                    <span className="flex items-center gap-1.5">
                      {d.name}
                      {d.is_usb && (
                        <span className="px-1.5 py-0.5 text-[9px] bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded font-semibold uppercase tracking-wider">
                          USB
                        </span>
                      )}
                    </span>
                    <span className="text-indigo-400">{d.disk_type}</span>
                  </div>
                  <div className="text-[11px] text-zinc-400 flex justify-between">
                    <span>Model: {d.model}</span>
                    <span>{getFormatSize(d.size)}</span>
                  </div>
                  <div className="text-[10px] text-zinc-500">
                    Type: {d.rotational ? 'Rotational HDD' : 'Solid State Drive (SSD)'}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {isKiosk && storageInfo && (
          <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-2xl space-y-4 animate-fade-in">
            <div className="flex justify-between items-center">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <HardDrive size={16} className="text-indigo-400" />
                Local Backup Storage
              </h3>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-bold ${
                storageInfo.is_mounted 
                  ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
                  : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
              }`}>
                {storageInfo.is_mounted ? 'USB Mount' : 'Fallback (/)'}
              </span>
            </div>
            
            <div className="space-y-3">
              <div className="flex justify-between text-xs text-zinc-400">
                <span>Mount Path</span>
                <span className="font-mono text-zinc-300 text-right max-w-[150px] truncate" title={storageInfo.path}>
                  {storageInfo.path}
                </span>
              </div>
              
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs font-semibold">
                  <span className="text-zinc-400">Used Space ({getFormatSize(storageInfo.used)})</span>
                  <span className="text-white">
                    {((storageInfo.used / storageInfo.total) * 100).toFixed(0)}%
                  </span>
                </div>
                
                <div className="w-full bg-zinc-950 h-2 rounded-full overflow-hidden border border-zinc-800/80 p-[1px]">
                  <div 
                    className={`h-full rounded-full transition-all duration-500 ${
                      (storageInfo.free / storageInfo.total) < 0.1 
                        ? 'bg-rose-500' 
                        : (storageInfo.free / storageInfo.total) < 0.25 
                          ? 'bg-amber-500' 
                          : 'bg-indigo-500'
                    }`}
                    style={{ width: `${(storageInfo.used / storageInfo.total) * 100}%` }}
                  />
                </div>
              </div>
              
              <div className="flex justify-between text-xs font-semibold">
                <span className="text-zinc-400">Free Space</span>
                <span className="text-emerald-400">{getFormatSize(storageInfo.free)}</span>
              </div>
              
              <div className="flex justify-between text-xs">
                <span className="text-zinc-400">Total Capacity</span>
                <span className="text-zinc-300 font-semibold">{getFormatSize(storageInfo.total)}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

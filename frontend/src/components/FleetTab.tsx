import React, { useState, useEffect } from 'react';
import { Plus, Settings as Gear, ShieldAlert, CheckCircle, RefreshCw, Terminal, AlertTriangle, Trash2 } from 'lucide-react';

interface Node {
  id: number;
  hostname: string;
  ip_address: string;
  ssh_port: number;
  status: string;
  last_backup: string | null;
  disk_type: string;
  network_iface: string | null;
  efi_uuid: string | null;
}

interface FleetTabProps {
  onViewLogs: (taskId: string, title: string) => void;
}

export default function FleetTab({ onViewLogs }: FleetTabProps) {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);

  // Form State
  const [hostname, setHostname] = useState('');
  const [ipAddress, setIpAddress] = useState('');
  const [sshPort, setSshPort] = useState(2222);
  const [username, setUsername] = useState('user');
  const [password, setPassword] = useState('admin');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const fetchNodes = async () => {
    try {
      const res = await fetch('/api/nodes');
      const data = await res.json();
      setNodes(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchNodes();
    const interval = setInterval(fetchNodes, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleAddNode = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const res = await fetch('/api/nodes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          hostname,
          ip_address: ipAddress,
          ssh_port: sshPort,
          bootstrap_user: username,
          bootstrap_password: password
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to add node');

      setShowAddModal(false);
      setHostname('');
      setIpAddress('');
      setPassword('');
      fetchNodes();
      
      // Open logs for the bootstrap task
      if (data.task_id) {
        onViewLogs(data.task_id, `Bootstrapping ${hostname}`);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const runPrepare = async (nodeId: number, name: string) => {
    try {
      const res = await fetch(`/api/nodes/${nodeId}/prepare`, { method: 'POST' });
      const data = await res.json();
      if (data.task_id) {
        onViewLogs(data.task_id, `Preparing Node ${name}`);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const runBackup = async (nodeId: number, name: string) => {
    try {
      const res = await fetch(`/api/nodes/${nodeId}/backup`, { method: 'POST' });
      const data = await res.json();
      if (data.task_id) {
        onViewLogs(data.task_id, `Backing up Node ${name}`);
      }
    } catch (e) {
      console.error(e);
    }
  };

  const handleDeleteNode = async (nodeId: number, name: string) => {
    if (!window.confirm(`Are you sure you want to delete node "${name}"? This will also remove its backup history.`)) {
      return;
    }
    try {
      const res = await fetch(`/api/nodes/${nodeId}`, { method: 'DELETE' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to delete node');
      }
      fetchNodes();
    } catch (e: any) {
      alert(e.message);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'READY':
        return <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"><CheckCircle size={14} /> Ready [Labels OK]</span>;
      case 'NEEDS_FIX':
        return <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20"><AlertTriangle size={14} /> Needs Fix [No labels]</span>;
      case 'NEEDS_BOOTSTRAP':
        return <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-zinc-500/10 text-zinc-400 border border-zinc-500/20"><Gear size={14} /> Needs Provisioning</span>;
      case 'OFFLINE':
      default:
        return <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20"><ShieldAlert size={14} /> Offline</span>;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white">Edge Fleet</h2>
          <p className="text-sm text-zinc-400">Manage and auto-provision your active Debian edge nodes.</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-medium transition-colors"
        >
          <Plus size={18} /> Add Node
        </button>
      </div>

      <div className="overflow-x-auto rounded-xl border border-zinc-800 bg-zinc-900/50 backdrop-blur-md">
        <table className="min-w-full divide-y divide-zinc-800 text-left text-sm text-zinc-300">
          <thead className="bg-zinc-900 text-xs uppercase tracking-wider text-zinc-400">
            <tr>
              <th className="px-6 py-4">Hostname</th>
              <th className="px-6 py-4">IP Address</th>
              <th className="px-6 py-4">Disk & Interface</th>
              <th className="px-6 py-4">Status</th>
              <th className="px-6 py-4">Last Backup</th>
              <th className="px-6 py-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-zinc-500">Loading fleet data...</td>
              </tr>
            ) : nodes.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-zinc-500">No nodes added yet. Add a node to start.</td>
              </tr>
            ) : (
              nodes.map((node) => (
                <tr key={node.id} className="hover:bg-zinc-800/30 transition-colors">
                  <td className="px-6 py-4 font-semibold text-white">{node.hostname}</td>
                  <td className="px-6 py-4 text-zinc-400">{node.ip_address}:{node.ssh_port}</td>
                  <td className="px-6 py-4">
                    <div className="flex flex-col">
                      <span className="text-zinc-300 font-medium text-xs">Disk: {node.disk_type}</span>
                      <span className="text-zinc-500 text-xs">Net: {node.network_iface || 'UNKNOWN'}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4">{getStatusBadge(node.status)}</td>
                  <td className="px-6 py-4 text-zinc-400">
                    {node.last_backup ? new Date(node.last_backup).toLocaleString() : 'Never'}
                  </td>
                  <td className="px-6 py-4 text-right flex items-center justify-end gap-2">
                    <button
                      onClick={() => runPrepare(node.id, node.hostname)}
                      disabled={node.status === 'NEEDS_BOOTSTRAP' || node.status === 'OFFLINE'}
                      className="px-3 py-1.5 text-xs font-semibold bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 rounded border border-amber-500/20 disabled:opacity-30 transition-colors"
                    >
                      Prepare Disk
                    </button>
                    <button
                      onClick={() => runBackup(node.id, node.hostname)}
                      disabled={node.status !== 'READY'}
                      className="px-3 py-1.5 text-xs font-semibold bg-indigo-500/10 hover:bg-indigo-500/20 text-indigo-400 rounded border border-indigo-500/20 disabled:opacity-30 transition-colors"
                    >
                      Backup Now
                    </button>
                    <button
                      onClick={() => handleDeleteNode(node.id, node.hostname)}
                      className="p-1.5 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 rounded border border-rose-500/20 transition-colors"
                      title="Delete Node"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md p-6 bg-zinc-900 border border-zinc-800 rounded-2xl shadow-xl space-y-4">
            <h3 className="text-lg font-bold text-white">Add Node (Auto-Provision)</h3>
            <form onSubmit={handleAddNode} className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">Hostname</label>
                <input
                  type="text"
                  required
                  placeholder="edge-node-01"
                  value={hostname}
                  onChange={(e) => setHostname(e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-white text-sm focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">IP Address</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. 192.168.1.10, 192.168.1.50-60, 192.168.2.0/24"
                  value={ipAddress}
                  onChange={(e) => setIpAddress(e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-white text-sm focus:border-indigo-500 focus:outline-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1">SSH Port</label>
                  <input
                    type="number"
                    value={sshPort}
                    onChange={(e) => setSshPort(parseInt(e.target.value))}
                    className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-white text-sm focus:border-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1">Bootstrap User</label>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-white text-sm focus:border-indigo-500 focus:outline-none"
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">Temporary Password (escalation)</label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-white text-sm focus:border-indigo-500 focus:outline-none"
                />
              </div>

              {error && <div className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 p-2.5 rounded-lg">{error}</div>}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 text-sm font-semibold text-zinc-400 bg-zinc-800/50 hover:bg-zinc-800 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg disabled:opacity-50 transition-colors"
                >
                  {submitting ? 'Registering...' : 'Provision Now'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { Database, TrendingDown, ArrowDownCircle, RefreshCw } from 'lucide-react';

interface Stats {
  total_nodes: number;
  total_original_size_bytes: number;
  total_deduplicated_size_bytes: number;
  deduplication_ratio: number;
}

interface BackupHistory {
  id: number;
  node_id: number;
  archive_name: string;
  timestamp: string;
  original_size: number;
  deduplicated_size: number;
  status: string;
}

interface Node {
  id: number;
  hostname: string;
}

export default function HistoryTab() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [history, setHistory] = useState<BackupHistory[]>([]);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchStats = async () => {
    try {
      const statsRes = await fetch('/api/stats');
      const statsData = await statsRes.json();
      setStats(statsData);

      const nodesRes = await fetch('/api/nodes');
      const nodesData = await nodesRes.json();
      setNodes(nodesData);

      // Fetch backup history for all nodes
      const allHistory: BackupHistory[] = [];
      for (const n of nodesData) {
        const histRes = await fetch(`/api/nodes/${n.id}/history`);
        const histData = await histRes.json();
        allHistory.push(...histData);
      }
      // Sort history by date descending
      allHistory.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      setHistory(allHistory);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  const getFormatSize = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  };

  const getNodeName = (nodeId: number) => {
    const node = nodes.find(n => n.id === nodeId);
    return node ? node.hostname : `Node #${nodeId}`;
  };

  const getSavedSpace = () => {
    if (!stats) return '0 B';
    const diff = stats.total_original_size_bytes - stats.total_deduplicated_size_bytes;
    return getFormatSize(Math.max(0, diff));
  };

  return (
    <div className="space-y-6">
      {/* Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-2xl flex items-center gap-4">
          <div className="p-3.5 bg-indigo-500/10 text-indigo-400 rounded-xl border border-indigo-500/20">
            <Database size={24} />
          </div>
          <div>
            <p className="text-xs text-zinc-400 font-medium uppercase tracking-wider">Total Repository Data</p>
            <h4 className="text-xl font-bold text-white mt-1">
              {stats ? getFormatSize(stats.total_deduplicated_size_bytes) : '0 B'}
            </h4>
            <p className="text-[10px] text-zinc-500 mt-0.5">Physical size on central storage</p>
          </div>
        </div>

        <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-2xl flex items-center gap-4">
          <div className="p-3.5 bg-emerald-500/10 text-emerald-400 rounded-xl border border-emerald-500/20">
            <ArrowDownCircle size={24} />
          </div>
          <div>
            <p className="text-xs text-zinc-400 font-medium uppercase tracking-wider">Original System Size</p>
            <h4 className="text-xl font-bold text-white mt-1">
              {stats ? getFormatSize(stats.total_original_size_bytes) : '0 B'}
            </h4>
            <p className="text-[10px] text-emerald-400 mt-0.5">Total size before deduplication</p>
          </div>
        </div>

        <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-2xl flex items-center gap-4">
          <div className="p-3.5 bg-purple-500/10 text-purple-400 rounded-xl border border-purple-500/20">
            <TrendingDown size={24} />
          </div>
          <div>
            <p className="text-xs text-zinc-400 font-medium uppercase tracking-wider">Storage Savings</p>
            <h4 className="text-xl font-bold text-white mt-1">{getSavedSpace()}</h4>
            <p className="text-[10px] text-purple-400 mt-0.5">
              Dedup Ratio: {stats ? stats.deduplication_ratio : '1.0'}x
            </p>
          </div>
        </div>
      </div>

      {/* History log list */}
      <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-2xl space-y-4">
        <div className="flex justify-between items-center">
          <div>
            <h3 className="text-lg font-bold text-white">Execution History</h3>
            <p className="text-xs text-zinc-400">View recent backup metrics, sizes, and execution statuses.</p>
          </div>
          <button
            onClick={fetchStats}
            className="p-1.5 hover:bg-zinc-800 text-zinc-400 hover:text-white rounded transition-colors"
          >
            <RefreshCw size={16} />
          </button>
        </div>

        <div className="overflow-x-auto rounded-xl border border-zinc-800/80 bg-zinc-950">
          <table className="min-w-full divide-y divide-zinc-800 text-left text-xs text-zinc-300">
            <thead className="bg-zinc-900 text-zinc-400 uppercase tracking-wider font-semibold">
              <tr>
                <th className="px-6 py-3.5">Archive Snapshot</th>
                <th className="px-6 py-3.5">Origin Node</th>
                <th className="px-6 py-3.5">Date & Time</th>
                <th className="px-6 py-3.5">Original Size</th>
                <th className="px-6 py-3.5">Deduplicated Size</th>
                <th className="px-6 py-3.5">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {loading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-zinc-500">Loading history records...</td>
                </tr>
              ) : history.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-zinc-500">No backup records found.</td>
                </tr>
              ) : (
                history.map((h) => (
                  <tr key={h.id} className="hover:bg-zinc-900/40 transition-colors">
                    <td className="px-6 py-4 font-semibold text-white">{h.archive_name}</td>
                    <td className="px-6 py-4 text-zinc-400">{getNodeName(h.node_id)}</td>
                    <td className="px-6 py-4 text-zinc-400">{new Date(h.timestamp).toLocaleString()}</td>
                    <td className="px-6 py-4 text-zinc-300">{getFormatSize(h.original_size)}</td>
                    <td className="px-6 py-4 text-zinc-300">{getFormatSize(h.deduplicated_size)}</td>
                    <td className="px-6 py-4">
                      {h.status === 'SUCCESS' ? (
                        <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Success</span>
                      ) : (
                        <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">Failed</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

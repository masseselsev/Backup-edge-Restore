import React, { useState, useEffect } from 'react';
import { Download, Cpu, RefreshCw, CheckCircle, ShieldAlert } from 'lucide-react';
import TaskLogsModal from './TaskLogsModal';

interface IsoStatus {
  base_iso_cached: boolean;
  client_iso_ready: boolean;
  base_iso_progress?: number;
}

export default function ClientIsoTab() {
  const [status, setStatus] = useState<IsoStatus | null>(null);
  const [orchestratorIp, setOrchestratorIp] = useState(window.location.hostname);
  const [authToken, setAuthToken] = useState('offline-token-1234');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isDownloadingBase, setIsDownloadingBase] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);

  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/iso/status');
      const data = await res.json();
      setStatus(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsGenerating(true);
    setError('');
    setSuccessMsg('');
    try {
      const res = await fetch('/api/iso/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_ip: orchestratorIp,
          auth_token: authToken
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to start generation');
      
      if (data.task_id) {
        setActiveTaskId(data.task_id);
      } else {
        setSuccessMsg('ISO Generation task started in background.');
      }
      
      // Start polling faster
      setTimeout(fetchStatus, 3000);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleCacheBaseIso = async () => {
    setIsDownloadingBase(true);
    try {
      const res = await fetch('/api/iso/download_base', { method: 'POST' });
      if (!res.ok) throw new Error('Failed to start base ISO download');
      setSuccessMsg('Base ISO download started in the background. It may take several minutes depending on network speed.');
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsDownloadingBase(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3 mb-8">
        <div className="p-3 bg-indigo-500/10 border border-indigo-500/20 rounded-xl">
          <Cpu className="text-indigo-400" size={24} />
        </div>
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight">Technician Live-USB Generator</h2>
          <p className="text-xs text-zinc-400 mt-1">Generate a bootable Debian Live client for offline fleet restoration and disk wiping.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Configuration Panel */}
        <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-2xl space-y-4 shadow-xl">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            Configuration Payload
          </h3>
          <p className="text-xs text-zinc-400 mb-4">
            These settings will be injected into the Live-USB so the offline client can seamlessly sync with this orchestrator when plugged into the local network.
          </p>

          <form onSubmit={handleGenerate} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1.5">Target Orchestrator IP / Domain</label>
              <input
                type="text"
                required
                value={orchestratorIp}
                onChange={(e) => setOrchestratorIp(e.target.value)}
                className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-white text-sm focus:border-indigo-500 focus:outline-none transition-colors"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1.5">API Authentication Token</label>
              <input
                type="text"
                required
                value={authToken}
                onChange={(e) => setAuthToken(e.target.value)}
                className="w-full px-3 py-2 bg-zinc-950 border border-zinc-800 rounded-lg text-white text-sm focus:border-indigo-500 focus:outline-none transition-colors"
              />
            </div>

            {error && <div className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/20 p-3 rounded-lg">{error}</div>}
            {successMsg && <div className="text-xs text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 p-3 rounded-lg">{successMsg}</div>}

            <button
              type="submit"
              disabled={isGenerating || !status?.base_iso_cached}
              className="w-full flex items-center justify-center gap-2 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-bold text-sm tracking-wide shadow-lg disabled:opacity-50 transition-all"
            >
              {isGenerating ? <RefreshCw className="animate-spin" size={18} /> : <Cpu size={18} />}
              GENERATE LIVE-USB
            </button>
          </form>
        </div>

        {/* Status & Download Panel */}
        <div className="space-y-6">
          <div className="p-6 bg-zinc-900 border border-zinc-800 rounded-2xl shadow-xl">
            <h3 className="text-sm font-bold text-white mb-4">Pipeline Status</h3>
            
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 bg-zinc-950 border border-zinc-800/80 rounded-xl">
                <div>
                  <div className="text-xs font-bold text-white">Base Debian ISO Cache</div>
                  <div className="text-[10px] text-zinc-500">debian-live-testing-amd64-xfce.iso</div>
                  
                  {/* Progress Bar for Base ISO Download */}
                  {status?.base_iso_progress !== undefined && status.base_iso_progress > 0 && !status.base_iso_cached && (
                    <div className="mt-2 w-full max-w-[200px]">
                      <div className="flex justify-between items-center text-[10px] font-semibold mb-1">
                        <span className="text-zinc-400">
                          {status.base_iso_progress === 100 ? 'Validating checksum...' : 'Downloading...'}
                        </span>
                        <span className="text-sky-400">{status.base_iso_progress}%</span>
                      </div>
                      <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-gradient-to-r from-sky-400 to-indigo-500 rounded-full transition-all duration-1000 ease-out"
                          style={{ width: `${status.base_iso_progress}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>
                {status?.base_iso_cached ? (
                  <CheckCircle className="text-emerald-400" size={20} />
                ) : (
                  <button
                    onClick={handleCacheBaseIso}
                    disabled={isDownloadingBase}
                    className="px-3 py-1 text-xs font-bold bg-zinc-800 hover:bg-zinc-700 text-white rounded-md transition-colors"
                  >
                    {isDownloadingBase ? 'DOWNLOADING...' : 'CACHE NOW'}
                  </button>
                )}
              </div>

              <div className="flex items-center justify-between p-3 bg-zinc-950 border border-zinc-800/80 rounded-xl">
                <div>
                  <div className="text-xs font-bold text-white">Compiled Offline Client</div>
                  <div className="text-[10px] text-zinc-500">technician_client_v1.iso</div>
                </div>
                {status?.client_iso_ready ? (
                  <span className="px-2 py-1 text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 rounded uppercase">Ready</span>
                ) : (
                  <span className="px-2 py-1 text-[10px] font-bold bg-zinc-800 text-zinc-500 border border-zinc-700 rounded uppercase">Not Found</span>
                )}
              </div>
            </div>

            {status?.client_iso_ready && (
              <div className="mt-6">
                <a
                  href="/api/iso/download"
                  download
                  className="w-full flex items-center justify-center gap-2 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-bold text-sm tracking-wide shadow-lg transition-all"
                >
                  <Download size={18} />
                  DOWNLOAD ISO IMAGE
                </a>
                <p className="text-center text-[10px] text-zinc-500 mt-2">
                  Flash this image using Rufus or balenaEtcher.
                </p>
              </div>
            )}
          </div>
          
          <div className="p-4 bg-indigo-500/10 border border-indigo-500/20 rounded-xl flex items-start gap-3">
            <ShieldAlert className="text-indigo-400 shrink-0 mt-0.5" size={18} />
            <div className="text-xs text-indigo-200 leading-relaxed">
              <strong>Offline Capabilities:</strong> The Live-USB bundles the identical Flasher module used by this orchestrator. When booted, it will automatically launch a secure kiosk interface to allow untethered, high-speed disk restoration from local USB storage.
            </div>
          </div>
        </div>
      </div>

      {activeTaskId && (
        <TaskLogsModal
          taskId={activeTaskId}
          title="Live-USB Generation Progress"
          onClose={() => setActiveTaskId(null)}
        />
      )}
    </div>
  );
}

import React, { useState, useEffect, useRef } from 'react';
import { X, Terminal as TermIcon, CheckCircle, AlertCircle, Loader } from 'lucide-react';

interface TaskLogsModalProps {
  taskId: string;
  title: string;
  onClose: () => void;
}

export default function TaskLogsModal({ taskId, title, onClose }: TaskLogsModalProps) {
  const [status, setStatus] = useState('PENDING');
  const [logs, setLogs] = useState('');
  const terminalEndRef = useRef<HTMLDivElement>(null);

  const fetchLogs = async () => {
    try {
      const res = await fetch(`/api/tasks/${taskId}`);
      if (!res.ok) return;
      const data = await res.json();
      setStatus(data.status);
      setLogs(data.log_output);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(() => {
      if (status === 'PENDING' || status === 'RUNNING') {
        fetchLogs();
      } else {
        clearInterval(interval);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [taskId, status]);

  // Autoscroll
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const getStatusIndicator = () => {
    switch (status) {
      case 'SUCCESS':
        return <span className="inline-flex items-center gap-1 text-emerald-400 text-xs font-bold bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full"><CheckCircle size={12} /> Success</span>;
      case 'FAILED':
        return <span className="inline-flex items-center gap-1 text-rose-400 text-xs font-bold bg-rose-500/10 border border-rose-500/20 px-2 py-0.5 rounded-full"><AlertCircle size={12} /> Failed</span>;
      case 'RUNNING':
        return <span className="inline-flex items-center gap-1 text-sky-400 text-xs font-bold bg-sky-500/10 border border-sky-500/20 px-2 py-0.5 rounded-full"><Loader size={12} className="animate-spin" /> Running</span>;
      case 'PENDING':
      default:
        return <span className="inline-flex items-center gap-1 text-zinc-400 text-xs font-bold bg-zinc-500/10 border border-zinc-500/20 px-2 py-0.5 rounded-full"><Loader size={12} className="animate-spin" /> Pending</span>;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-3xl h-[80vh] flex flex-col bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="p-4 bg-zinc-900 border-b border-zinc-800 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <TermIcon className="text-zinc-400" size={18} />
            <span className="font-bold text-white text-sm">{title}</span>
            {getStatusIndicator()}
          </div>
          <button
            onClick={onClose}
            className="p-1 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Console logs */}
        <div className="flex-1 p-4 overflow-y-auto font-mono text-xs text-zinc-300 bg-black/95 select-text space-y-1">
          {logs ? (
            logs.split('\n').map((line, idx) => (
              <div key={idx} className="whitespace-pre-wrap leading-relaxed">
                {line}
              </div>
            ))
          ) : (
            <div className="text-zinc-600 italic">No output logs generated yet...</div>
          )}
          <div ref={terminalEndRef} />
        </div>
      </div>
    </div>
  );
}

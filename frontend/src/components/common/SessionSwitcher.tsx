import React, { useMemo } from 'react';
import { Plus, Trash2, Pencil } from 'lucide-react';
import { useChat } from '../../contexts/ChatContext';

const SessionSwitcher: React.FC = () => {
  const { sessions, activeSessionId, createSession, switchSession, deleteSession, renameSession } = useChat();

  const active = useMemo(() => sessions.find((s) => s.id === activeSessionId), [sessions, activeSessionId]);

  const startedText = active?.createdAt ? new Date(active.createdAt).toLocaleDateString() : '';

  return (
    <div className="flex flex-col items-start">
      <div className="flex items-center gap-2">
        <select
          className="glass-panel bg-darkGlass text-white rounded-lg px-3 py-2 border border-lightGlass"
          value={activeSessionId}
          onChange={(e) => switchSession(e.target.value)}
        >
          {sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title || 'Session'}
            </option>
          ))}
        </select>

        <button
          onClick={() => {
            const current = sessions.find((s) => s.id === activeSessionId);
            const next = window.prompt('New chat name:', current?.title || '');
            if (next !== null) renameSession(activeSessionId, next);
          }}
          className="p-2 rounded-lg bg-zinc-700 hover:bg-zinc-600 text-white"
          aria-label="Chat umbenennen"
          title="Chat umbenennen"
        >
          <Pencil size={16} />
        </button>

        <button
          onClick={createSession}
          className="p-2 rounded-lg bg-gradient-to-r from-limeGlow to-aquaGlow text-background"
          aria-label="New session"
          title="New session"
        >
          <Plus size={16} />
        </button>

        <button
          onClick={() => deleteSession(activeSessionId)}
          className="p-2 rounded-lg bg-red-600/80 hover:bg-red-600 text-white"
          aria-label="Delete session"
          title="Delete session"
        >
          <Trash2 size={16} />
        </button>
      </div>
      {startedText && (
        <div className="ml-1 mt-1 text-[10px] text-white/60">
          Started: {startedText}
        </div>
      )}
    </div>
  );
};

export default SessionSwitcher;



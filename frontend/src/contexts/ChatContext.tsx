import React, { createContext, useContext, useState, useCallback, ReactNode, useEffect, useRef } from 'react';
import { askSubstrateAI } from '../lib/askSubstrateAI';
import { normalizeAssistant } from '../lib/normalizeAssistant';
import { Message, ChatSession } from '../types';
import { detectDrifts } from '../lib/memory';
import { pushDrift } from '../lib/memory';

interface ChatContextProps {
  messages: Message[];
  isLoading: boolean;
  sendMessage: (content: string, mediaData?: string, mediaType?: string) => Promise<void>;
  clearMessages: () => void;
  reloadMessages: () => Promise<void>;  // 🔥 NEW: Reload messages from backend!
  sessions: ChatSession[];
  activeSessionId: string;
  createSession: () => void;
  switchSession: (id: string) => void;
  deleteSession: (id: string) => void;
  exportActiveSession: () => void;
  saveForLater: () => Promise<void>;
  renameSession: (id: string, title: string) => void;
  model: string;
  setModel: (model: string) => void;
  disablePresenceSeed: boolean;
  setDisablePresenceSeed: (v: boolean) => void;
  disableNormalizer: boolean;
  setDisableNormalizer: (v: boolean) => void;
  disableCorePrompt: boolean;
  setDisableCorePrompt: (v: boolean) => void;
}

const ChatContext = createContext<ChatContextProps | undefined>(undefined);

const STORAGE_KEY = 'substrate.chat.sessions.v1';

// No initial seed; sessions start empty

function bootstrapSession(): ChatSession {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    title: 'New Session',
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
}

export const ChatProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  // Agent-bound session (always "default") - 🏴‍☠️ FORCED FOR POSTGRESQL!
  const AGENT_SESSION_ID = 'default';
  
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    return [{
      id: AGENT_SESSION_ID,
      title: "Assistant's Consciousness",
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messages: [], // Will be loaded from backend!
    }];
  });

  // 🏴‍☠️ ALWAYS use "default" - no session switching for now!
  const activeSessionId = AGENT_SESSION_ID;  // Force default!
  const [_unusedActiveSessionId, setActiveSessionId] = useState<string>(AGENT_SESSION_ID);
  
  // 🔥 Load conversation from backend (can be called manually!)
  const reloadMessages = useCallback(async () => {
    try {
      console.log('🔄 RELOAD: Starting message reload...');
      const response = await fetch(`http://localhost:8284/api/conversation/${AGENT_SESSION_ID}?limit=1000`);
      if (!response.ok) {
        console.error('❌ RELOAD: Failed to load conversation from backend');
        return;
      }
      
      const data = await response.json();
      const backendMessages = data.messages || [];
      
      console.log(`📬 RELOAD: Loaded ${backendMessages.length} messages from backend`);
      
      // Convert backend format to frontend format
      const messages: Message[] = backendMessages.map((msg: any) => ({
        role: msg.role as 'user' | 'assistant' | 'system',  // Include system messages!
        content: msg.content,
        message_type: msg.message_type || (msg.role === 'system' ? 'system' : 'inbox'),  // Preserve message_type!
        // Preserve thinking/toolCalls if present
        thinking: msg.thinking,
        toolCalls: msg.tool_calls,
        reasoningTime: msg.reasoning_time
      }));
      
      console.log('✅ RELOAD: Updating sessions state...');
      // Update session with loaded messages
      setSessions([{
        id: AGENT_SESSION_ID,
        title: "Assistant's Consciousness",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        messages: messages,
      }]);
      console.log('✅ RELOAD: Complete!');
    } catch (error) {
      console.error('❌ RELOAD: Error loading conversation:', error);
    }
  }, [AGENT_SESSION_ID]);
  
  // Load conversation on mount!
  useEffect(() => {
    reloadMessages();
  }, []); // Load once on mount

  // Model state - fetch from backend (not localStorage!)
  // DEFAULT model (will be overridden by backend fetch)
  const [model, setModel] = useState<string>('qwen/qwen3-235b-a22b-thinking-2507');

  const [disablePresenceSeed, setDisablePresenceSeed] = useState<boolean>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      const parsed = JSON.parse(raw) as { disablePresenceSeed?: boolean };
      return Boolean(parsed.disablePresenceSeed);
    } catch {
      return false;
    }
  });

  const [disableNormalizer, setDisableNormalizer] = useState<boolean>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      const parsed = JSON.parse(raw) as { disableNormalizer?: boolean };
      return Boolean(parsed.disableNormalizer);
    } catch {
      return false;
    }
  });

  const [disableCorePrompt, setDisableCorePrompt] = useState<boolean>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      const parsed = JSON.parse(raw) as { disableCorePrompt?: boolean };
      return Boolean(parsed.disableCorePrompt);
    } catch {
      return false;
    }
  });

  // 🔥 SYNC MODEL FROM BACKEND SETTINGS
  useEffect(() => {
    const fetchModelFromBackend = async () => {
      try {
        const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8284';
        const response = await fetch(`${API_URL}/api/agents/default/config`);
        if (response.ok) {
          const data = await response.json();
          if (data.model) {
            console.log(`🔄 Syncing model from backend: ${data.model}`);
            setModel(data.model);
            // Update localStorage too
            try {
              const raw = localStorage.getItem(STORAGE_KEY);
              if (raw) {
                const parsed = JSON.parse(raw);
                parsed.model = data.model;
                localStorage.setItem(STORAGE_KEY, JSON.stringify(parsed));
              }
            } catch (e) {
              console.error('Failed to update localStorage:', e);
            }
          }
        }
      } catch (error) {
        console.error('Failed to sync model from backend:', error);
      }
    };
    
    // Fetch on mount
    fetchModelFromBackend();
    
    // Poll every 60 seconds to stay in sync (reduced from 3s - page reloads on save!)
    const interval = setInterval(fetchModelFromBackend, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!activeSessionId && sessions.length) {
      setActiveSessionId(sessions[0].id);
    }
  }, [activeSessionId, sessions]);

  const active = sessions.find((s) => s.id === activeSessionId) || sessions[0];

  const [messages, setMessages] = useState<Message[]>(active?.messages || []);
  const [isLoading, setIsLoading] = useState(false);
  const [lastUserAt, setLastUserAt] = useState<number>(() => Date.now());
  
  // Ref to always have the latest messages (prevents stale closure issues!)
  const messagesRef = useRef<Message[]>(active?.messages || []);

  // No more localStorage! Conversations are stored in backend DB! 🎯

  // Sync messages when switching sessions
  useEffect(() => {
    const current = sessions.find((s) => s.id === activeSessionId) || sessions[0];
    if (current) {
      setMessages(current.messages);
      messagesRef.current = current.messages; // Keep ref in sync!
    }
  }, [activeSessionId, sessions]);
  
  // Keep messagesRef in sync with messages state
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // Fetch model from backend on mount
  useEffect(() => {
    const fetchModel = async () => {
      try {
        const response = await fetch('http://localhost:8284/api/agents/default/config');
        if (response.ok) {
          const data = await response.json();
          if (data.model) {
            console.log('✅ Fetched model from backend:', data.model);
            setModel(data.model);
          }
        }
      } catch (error) {
        console.error('Failed to fetch model from backend:', error);
        // Keep default fallback
      }
    };
    fetchModel();
  }, []); // Run once on mount

  // Sessions start empty; no auto-greet

  const clearMessages = useCallback(async () => {
    try {
      // Clear messages in backend
      const response = await fetch(`http://localhost:8284/api/conversation/${AGENT_SESSION_ID}/clear`, {
        method: 'POST'
      });
      
      if (response.ok) {
        console.log('✅ Cleared conversation in backend');
        // Clear frontend state
        setMessages([]);
        setSessions([{
          id: AGENT_SESSION_ID,
          title: "Assistant's Consciousness",
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          messages: [],
        }]);
      }
    } catch (error) {
      console.error('Failed to clear conversation:', error);
    }
  }, [AGENT_SESSION_ID]);

  const sendMessage = useCallback(
    async (content: string, mediaData?: string, mediaType?: string) => {
      try {
        const userMessage: Message = { role: 'user', content };
        
        // CRITICAL FIX: Use ref to get ALWAYS the latest messages (no stale closure!)
        const currentMessages = messagesRef.current;
        const updatedMessages = [...currentMessages, userMessage];
        
        // Update both state and ref
        setMessages(updatedMessages);
        messagesRef.current = updatedMessages;
        setLastUserAt(Date.now());
        setIsLoading(true);
        
        // 🚫 NO STREAMING! Use normal endpoint for reliable message persistence!
        // This ensures all messages are properly saved to PostgreSQL!
        const result = await askSubstrateAI(updatedMessages, activeSessionId, model);

        // Update final message with complete result
        setMessages((prev) => {
          const updated = [...prev];
          const lastMsg = updated[updated.length - 1];
          if (lastMsg && lastMsg.role === 'assistant') {
            lastMsg.content = result.content;
            lastMsg.thinking = result.thinking || undefined;
            lastMsg.toolCalls = result.toolCalls || undefined;
            lastMsg.reasoningTime = result.reasoningTime;
          }
          messagesRef.current = updated;  // Sync ref!
          return updated;
        });
        
        // Dispatch request completion event (for CostCounter!)
        if (result.usage && result.usage.total_tokens > 0) {
          const requestEvent = new CustomEvent('request-complete', {
            detail: {
              prompt_tokens: result.usage.prompt_tokens,
              completion_tokens: result.usage.completion_tokens,
              total_tokens: result.usage.total_tokens,
              cost: result.usage.cost
            }
          });
          window.dispatchEvent(requestEvent);
        }
        
        // Add assistant message
        setMessages((prev) => [...prev, assistantMessage]);

        // Minimal drift detection on assistant output (fire-and-forget)
        try {
          const drifts = detectDrifts(result.content);
          if (drifts.length) {
            const assistantIndex = updatedMessages.length; // index within session after adding assistant
            const messageId = `${activeSessionId}_${assistantIndex}`;
            const ts = new Date().toISOString();
            // Base drifts
            for (const d of drifts) {
              // do not block UI; log and continue
              pushDrift({
                sessionId: activeSessionId,
                messageId,
                driftId: crypto.randomUUID(),
                ts,
                kind: d.kind,
                severity: d.severity,
              }).catch(() => {});
            }
            // Drip-logger: if watchdog triggered, log "drip" drift with higher severity
            if (result.flags?.watchdog) {
              pushDrift({
                sessionId: activeSessionId,
                messageId,
                driftId: crypto.randomUUID(),
                ts,
                kind: 'drip',
                severity: 4,
              }).catch(() => {});
            }
          }
        } catch {
          // ignore drift errors
        }

        setSessions((prev) =>
          prev.map((s) => {
            if (s.id !== activeSessionId) return s;
            const next: ChatSession = {
              ...s,
              messages: [...updatedMessages, assistantMessage],
              updatedAt: new Date().toISOString(),
            };
            if (s.title === 'New Session' && content) {
              next.title = content.slice(0, 40);
            }
            return next;
          })
        );
      } catch (error) {
        console.error('Error sending message:', error);
        // Remove "Thinking..." placeholder if error occurred
        setMessages((prev) => {
          const newMessages = [...prev];
          const lastIndex = newMessages.length - 1;
          if (lastIndex >= 0 && newMessages[lastIndex].content === 'Thinking...') {
            newMessages.pop(); // Remove thinking placeholder
          }
          return newMessages;
        });
        // Show error message
        setMessages((prev) => [
          ...prev,
          { 
            role: 'assistant', 
            content: `Sorry, I encountered an error: ${error instanceof Error ? error.message : 'Unknown error'}. Please try again later.` 
          },
        ]);
      } finally {
        setIsLoading(false);
      }
    },
    [activeSessionId, model] // Removed 'messages' from deps - we read it from state directly!
  );

  // OLD clearMessages moved to top (Backend-aware version)

  const createSession = useCallback(() => {
    const s = bootstrapSession();
    setSessions((prev) => [s, ...prev]);
    setActiveSessionId(s.id);
  }, []);

  const switchSession = useCallback((id: string) => {
    setActiveSessionId(id);
  }, []);

  const deleteSession = useCallback(
    (id: string) => {
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (id === activeSessionId) {
        setTimeout(() => {
          setSessions((cur) => {
            const remaining = cur.filter((s) => s.id !== id);
            if (remaining.length) {
              setActiveSessionId(remaining[0].id);
              return remaining;
            }
            const next = bootstrapSession();
            setActiveSessionId(next.id);
            return [next];
          });
        }, 0);
      }
    },
    [activeSessionId]
  );

  const renameSession = useCallback((id: string, title: string) => {
    setSessions((prev) =>
      prev.map((s) =>
        s.id === id
          ? {
              ...s,
              title: (title || '').trim().slice(0, 60),
              updatedAt: new Date().toISOString(),
            }
          : s
      )
    );
  }, []);

  const exportActiveSession = useCallback(() => {
    const current = sessions.find((s) => s.id === activeSessionId);
    if (!current) return;
    const payload = {
      id: current.id,
      title: current.title,
      createdAt: current.createdAt,
      updatedAt: current.updatedAt,
      messages: current.messages,
    };
    const ts = new Date().toISOString().replace(/[:]/g, '-');
    const name = `substrate-session_${ts}.json`;
    import('../lib/download').then(({ downloadText }) => {
      downloadText(name, JSON.stringify(payload, null, 2));
    });
  }, [sessions, activeSessionId]);

  const saveForLater = useCallback(async () => {
    const current = sessions.find((s) => s.id === activeSessionId);
    if (!current) return;
    const ts = new Date().toISOString().replace(/[:]/g, '-');
    const safeTitle = (current.title || 'session').replace(/[^\p{L}\p{N}\-_ ]/gu, '').trim().replace(/\s+/g, '_');
    const filename = `${safeTitle || 'session'}_${ts}.json`;
    const payload = JSON.stringify({ ...current }, null, 2);
    const { saveToLocalFS } = await import('../lib/saveToLocalFS');
    await saveToLocalFS(filename, payload);
  }, [sessions, activeSessionId]);

  // Idle auto-save after 10 minutes without user messages (overwrite stable file)
  useEffect(() => {
    let timer: number | undefined;
    const autoSave = async () => {
      const current = sessions.find((s) => s.id === activeSessionId);
      if (!current) return;
      const created = new Date(current.createdAt);
      const y = created.getFullYear();
      const m = String(created.getMonth() + 1).padStart(2, '0');
      const d = String(created.getDate()).padStart(2, '0');
      const dateTag = `${y}-${m}-${d}`;
      const safeTitle = (current.title || 'session').replace(/[^\p{L}\p{N}\-_ ]/gu, '').trim().replace(/\s+/g, '_');
      const filename = `${safeTitle || 'session'}_${dateTag}.json`;
      const payload = JSON.stringify({ ...current }, null, 2);
      const { saveToLocalFS } = await import('../lib/saveToLocalFS');
      await saveToLocalFS(filename, payload);
    };
    const reset = () => {
      if (timer) window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        autoSave().catch(() => {});
      }, 10 * 60 * 1000);
    };
    reset();
    return () => {
      if (timer) window.clearTimeout(timer);
    };
  }, [lastUserAt, sessions, activeSessionId]);

  return (
    <ChatContext.Provider
      value={{
        messages,
        isLoading,
        sendMessage,
        clearMessages,
        reloadMessages,  // 🔥 Export reload function!
        sessions,
        activeSessionId,
        createSession,
        switchSession,
        deleteSession,
        exportActiveSession,
        saveForLater,
        renameSession,
        model,
        setModel,
        disablePresenceSeed,
        setDisablePresenceSeed,
        disableNormalizer,
        setDisableNormalizer,
        disableCorePrompt,
        setDisableCorePrompt,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
};

export const useChat = () => {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChat must be used within a ChatProvider');
  }
  return context;
};
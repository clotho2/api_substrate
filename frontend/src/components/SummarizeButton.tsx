import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { FileText } from 'lucide-react';
import { useChat } from '../contexts/ChatContext';

interface SummarizeButtonProps {
  sessionId: string;
}

const SummarizeButton: React.FC<SummarizeButtonProps> = ({ sessionId }) => {
  const { reloadMessages } = useChat();  // 🔥 Get reload function!
  const [isLoading, setIsLoading] = useState(false);
  const [lastResult, setLastResult] = useState<{ success: boolean; message?: string } | null>(null);

  const handleSummarize = async () => {
    setIsLoading(true);
    setLastResult(null);

    try {
      const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8284';
      const response = await fetch(`${API_URL}/api/conversation/${sessionId}/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });

      const data = await response.json();

      if (response.ok && data.success) {
        console.log('🎉 SUMMARY SUCCESS!', data);
        setLastResult({
          success: true,
          message: `✅ Summary created! ${data.message_count} messages summarized.`
        });
        
        // 🔥 Trigger token counter refresh + reload messages!
        console.log('📡 Dispatching summary-completed event...');
        window.dispatchEvent(new Event('summary-completed'));
        
        // Wait a moment for token counter to refresh, then reload messages
        setTimeout(async () => {
          console.log('🔄 Reloading messages...');
          await reloadMessages();
          console.log('✅ Messages reloaded after summary!');
        }, 1000);  // Increased to 1s
      } else {
        setLastResult({
          success: false,
          message: data.error || data.message || 'Error creating summary'
        });
      }
    } catch (error) {
      console.error('Summary error:', error);
      setLastResult({
        success: false,
        message: 'Connection error to backend'
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      {lastResult && (
        <motion.div
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -10 }}
          className={`text-xs px-2 py-1 rounded ${
            lastResult.success
              ? 'bg-green-900/30 text-green-400'
              : 'bg-red-900/30 text-red-400'
          }`}
        >
          {lastResult.message}
        </motion.div>
      )}
      
      <motion.button
        whileHover={{ scale: 1.05 }}
        whileTap={{ scale: 0.95 }}
        onClick={handleSummarize}
        disabled={isLoading}
        className="
          px-3 py-1.5 rounded-lg text-xs font-medium
          bg-yellow-900/30 border border-yellow-700/50 text-yellow-400
          hover:bg-yellow-900/50 hover:border-yellow-600/50
          disabled:opacity-50 disabled:cursor-not-allowed
          transition-colors flex items-center gap-1.5
        "
        title="Konversation zusammenfassen (manuell)"
      >
        {isLoading ? (
          <>
            <div className="w-3 h-3 border-2 border-yellow-400/30 border-t-yellow-400 rounded-full animate-spin" />
            <span>Zusammenfassen...</span>
          </>
        ) : (
          <>
            <FileText size={14} />
            <span>Zusammenfassen</span>
          </>
        )}
      </motion.button>
    </div>
  );
};

export default SummarizeButton;


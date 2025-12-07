import { useEffect, useState } from 'react';
import ChatScreen from './screens/ChatScreen';
import { setupNotifications } from './lib/notify';
import { ChatProvider } from './contexts/ChatContext';
import RadialBackground from './components/ui/RadialBackground';
import WelcomeModal from './components/WelcomeModal';

function App() {
  const [setupComplete, setSetupComplete] = useState(false);

  useEffect(() => {
    // Request notification permission and setup
    setupNotifications();
  }, []);

  const handleSetupComplete = () => {
    setSetupComplete(true);
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <RadialBackground />
      
      {/* Welcome Modal for first-time setup */}
      {!setupComplete && (
        <WelcomeModal onComplete={handleSetupComplete} />
      )}
      
      {/* Main App - only show after setup or if user skips */}
      {setupComplete && (
        <ChatProvider>
          <ChatScreen />
        </ChatProvider>
      )}
    </div>
  );
}

export default App;


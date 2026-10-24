import React, { useState } from "react";
import { AuthProvider } from "./context/AuthContext";
import { Sidebar } from "./components/layout/Sidebar";
import { Header } from "./components/layout/Header";
import { AssistantScreen } from "./components/assistant/AssistantScreen";
import { ConstructorScreen } from "./components/constructor/ConstructorScreen";
import { ComplianceScreen } from "./components/compliance/ComplianceScreen";
import { GovernanceScreen } from "./components/governance/GovernanceScreen";
import { ScreenId } from "./types/api";

export const App: React.FC = () => {
  const [activeScreen, setActiveScreen] = useState<ScreenId>("assistant");
  const [sessionId, setSessionId] = useState<string>(() => crypto.randomUUID());
  const [selectedTemplateCode, setSelectedTemplateCode] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(false);

  const handleResetSession = () => {
    setSessionId(crypto.randomUUID());
  };

  const handleNavigateScreen = (screen: ScreenId, templateCode?: string) => {
    if (templateCode) {
      setSelectedTemplateCode(templateCode);
    }
    setActiveScreen(screen);
  };

  return (
    <AuthProvider>
      <div className="flex h-screen w-screen overflow-hidden bg-[#07070B] text-slate-100">
        <Sidebar
          activeScreen={activeScreen}
          onSelectScreen={(s) => setActiveScreen(s)}
          onNewChat={handleResetSession}
          onQuickTemplateSelect={(code) => setSelectedTemplateCode(code)}
          collapsed={sidebarCollapsed}
          onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
        />

        <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
          <Header activeScreen={activeScreen} onSelectScreen={(s) => setActiveScreen(s)} />

          {activeScreen === "assistant" && (
            <AssistantScreen
              sessionId={sessionId}
              onResetSession={handleResetSession}
              onNavigateScreen={handleNavigateScreen}
            />
          )}

          {activeScreen === "constructor" && (
            <ConstructorScreen initialModuleCode={selectedTemplateCode} />
          )}

          {activeScreen === "compliance" && <ComplianceScreen />}

          {activeScreen === "governance" && <GovernanceScreen />}
        </div>
      </div>
    </AuthProvider>
  );
};

export default App;

import React, { useCallback, useEffect, useState } from "react";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { Sidebar } from "./components/layout/Sidebar";
import { AssistantScreen } from "./components/assistant/AssistantScreen";
import { ConstructorScreen } from "./components/constructor/ConstructorScreen";
import { ComplianceScreen } from "./components/compliance/ComplianceScreen";
import { MatrixScreen } from "./components/matrix/MatrixScreen";
import { GovernanceScreen } from "./components/governance/GovernanceScreen";
import { AuthScreen } from "./components/auth/AuthScreen";
import { ChatSessionRecord, ChatTurn, ScreenId } from "./types/api";

const STORAGE_KEY = "cdo_assistant_chat_sessions_v1";

function loadSavedSessions(): ChatSessionRecord[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

const MainLayout: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const [activeScreen, setActiveScreen] = useState<ScreenId>("assistant");
  const [sessions, setSessions] = useState<ChatSessionRecord[]>(() => {
    const saved = loadSavedSessions();
    if (saved.length > 0) return saved;
    return [
      {
        id: crypto.randomUUID(),
        title: "Новый диалог",
        updatedAt: new Date().toISOString(),
        turns: [],
      },
    ];
  });
  const [activeSessionId, setActiveSessionId] = useState<string>(() => {
    const saved = loadSavedSessions();
    return saved[0]?.id || crypto.randomUUID();
  });

  const [selectedTemplateCode, setSelectedTemplateCode] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(false);

  // Ensure activeSessionId exists in sessions
  useEffect(() => {
    if (!sessions.some((s) => s.id === activeSessionId)) {
      if (sessions.length > 0) {
        setActiveSessionId(sessions[0].id);
      } else {
        const freshId = crypto.randomUUID();
        setSessions([
          {
            id: freshId,
            title: "Новый диалог",
            updatedAt: new Date().toISOString(),
            turns: [],
          },
        ]);
        setActiveSessionId(freshId);
      }
    }
  }, [sessions, activeSessionId]);

  // Persist non-empty sessions to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    } catch {
      // ignore storage quota errors
    }
  }, [sessions]);

  const handleNewChat = useCallback(() => {
    // Reuse existing empty session if already on one
    const current = sessions.find((s) => s.id === activeSessionId);
    if (current && current.turns.length === 0) {
      return;
    }
    const newId = crypto.randomUUID();
    const newSession: ChatSessionRecord = {
      id: newId,
      title: "Новый диалог",
      updatedAt: new Date().toISOString(),
      turns: [],
    };
    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newId);
  }, [sessions, activeSessionId]);

  const handleUpdateTurns = useCallback(
    (sessionId: string, updater: (prev: ChatTurn[]) => ChatTurn[]) => {
      setSessions((prev) =>
        prev.map((sess) => {
          if (sess.id !== sessionId) return sess;
          const nextTurns = updater(sess.turns);
          const firstUserMsg = nextTurns.find((t) => t.role === "user")?.content;
          const nextTitle = firstUserMsg
            ? firstUserMsg.slice(0, 42) + (firstUserMsg.length > 42 ? "…" : "")
            : sess.title;
          return {
            ...sess,
            title: nextTitle,
            updatedAt: new Date().toISOString(),
            turns: nextTurns,
          };
        })
      );
    },
    []
  );

  const handleDeleteSession = useCallback(
    (id: string) => {
      setSessions((prev) => {
        const filtered = prev.filter((s) => s.id !== id);
        if (filtered.length === 0) {
          const freshId = crypto.randomUUID();
          return [
            {
              id: freshId,
              title: "Новый диалог",
              updatedAt: new Date().toISOString(),
              turns: [],
            },
          ];
        }
        return filtered;
      });
    },
    []
  );

  const handleNavigateScreen = (screen: ScreenId, templateCode?: string) => {
    if (templateCode) {
      setSelectedTemplateCode(templateCode);
    }
    setActiveScreen(screen);
  };

  if (!isAuthenticated) {
    return <AuthScreen />;
  }

  const activeSession = sessions.find((s) => s.id === activeSessionId);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#08080A] text-zinc-100">
      <Sidebar
        activeScreen={activeScreen}
        onSelectScreen={(s) => setActiveScreen(s)}
        onNewChat={handleNewChat}
        sessions={sessions}
        activeSessionId={activeSessionId}
        onSelectSession={(id) => setActiveSessionId(id)}
        onDeleteSession={handleDeleteSession}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((c) => !c)}
      />

      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        {activeScreen === "assistant" && (
          <AssistantScreen
            sessionId={activeSessionId}
            turns={activeSession?.turns || []}
            onUpdateTurns={handleUpdateTurns}
            onResetSession={handleNewChat}
            onNavigateScreen={handleNavigateScreen}
          />
        )}

        {activeScreen === "constructor" && (
          <ConstructorScreen initialModuleCode={selectedTemplateCode} />
        )}

        {activeScreen === "compliance" && <ComplianceScreen />}

        {activeScreen === "matrix" && <MatrixScreen />}

        {activeScreen === "governance" && <GovernanceScreen />}
      </div>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <MainLayout />
    </AuthProvider>
  );
};

export default App;

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { HealthResponse, UserRole } from "../types/api";
import { fetchHealth, issueRoleToken } from "../services/apiClient";

export interface RoleMeta {
  role: UserRole;
  label: string;
  shortLabel: string;
  clearance: string;
  description: string;
  badgeColor: string;
}

export const ROLE_METADATA: Record<UserRole, RoleMeta> = {
  employee: {
    role: "employee",
    label: "Сотрудник подразделения",
    shortLabel: "Сотрудник",
    clearance: "Обычный доступ",
    description: "Работа с инструкцией, заполнение шаблонов и проверка документов",
    badgeColor: "bg-slate-800 text-slate-200 border-white/15",
  },
  dou_specialist: {
    role: "dou_specialist",
    label: "Специалист делопроизводства",
    shortLabel: "Специалист ДОУ",
    clearance: "Служебный доступ",
    description: "Доступ к служебным документам и обновление версий инструкций",
    badgeColor: "bg-violet-500/20 text-violet-200 border-violet-500/40",
  },
  security_auditor: {
    role: "security_auditor",
    label: "Служба безопасности",
    shortLabel: "Безопасность",
    clearance: "Просмотр истории действий",
    description: "Просмотр истории всех запросов и проверка безопасности",
    badgeColor: "bg-amber-500/20 text-amber-200 border-amber-500/40",
  },
  admin: {
    role: "admin",
    label: "Администратор",
    shortLabel: "Администратор",
    clearance: "Полный доступ",
    description: "Полное управление документами, шаблонами и историей действий",
    badgeColor: "bg-rose-500/20 text-rose-200 border-rose-500/40",
  },
};

interface AuthContextValue {
  role: UserRole;
  username: string;
  token: string | null;
  health: HealthResponse | null;
  isSwitchingRole: boolean;
  switchRole: (targetRole: UserRole) => Promise<void>;
  refreshHealth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [role, setRole] = useState<UserRole>("employee");
  const [username, setUsername] = useState<string>("Сотрудник ЦДО");
  const [token, setToken] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isSwitchingRole, setIsSwitchingRole] = useState<boolean>(false);

  const refreshHealth = useCallback(async () => {
    try {
      const h = await fetchHealth();
      setHealth(h);
    } catch {
      setHealth({
        status: "offline",
        db_connected: false,
        ollama_connected: false,
        active_version: "1.0",
        timestamp: new Date().toISOString(),
      });
    }
  }, []);

  const switchRole = useCallback(async (targetRole: UserRole) => {
    setIsSwitchingRole(true);
    try {
      const roleTitle = ROLE_METADATA[targetRole].shortLabel;
      const res = await issueRoleToken(targetRole, roleTitle);
      setRole(targetRole);
      setUsername(res.username);
      setToken(res.access_token);
    } catch {
      // Fallback if backend is warming up
      setRole(targetRole);
      setUsername(`Демо (${ROLE_METADATA[targetRole].shortLabel})`);
    } finally {
      setIsSwitchingRole(false);
    }
  }, []);

  useEffect(() => {
    void refreshHealth();
    void switchRole("employee");
    const timer = setInterval(() => {
      void refreshHealth();
    }, 15000);
    return () => clearInterval(timer);
  }, [refreshHealth, switchRole]);

  return (
    <AuthContext.Provider
      value={{
        role,
        username,
        token,
        health,
        isSwitchingRole,
        switchRole,
        refreshHealth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return ctx;
}

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
  isAuthenticated: boolean;
  role: UserRole;
  username: string;
  token: string | null;
  health: HealthResponse | null;
  isSwitchingRole: boolean;
  login: (credentials: { role?: UserRole; username: string; password?: string }) => Promise<void>;
  logout: () => void;
  switchRole: (targetRole: UserRole, password?: string) => Promise<void>;
  refreshHealth: () => Promise<void>;
}

const AUTH_STORAGE_KEY = "cdo_auth_session_v2";

interface StoredSession {
  token: string;
  role: UserRole;
  username: string;
}

function isTokenExpired(token: string): boolean {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return false;
    const payload = JSON.parse(atob(parts[1]));
    if (!payload.exp) return false;
    return Date.now() >= payload.exp * 1000;
  } catch {
    return false;
  }
}

function loadStoredSession(): StoredSession | null {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || !parsed.token) return null;
    if (isTokenExpired(parsed.token)) {
      localStorage.removeItem(AUTH_STORAGE_KEY);
      return null;
    }
    return parsed as StoredSession;
  } catch {
    return null;
  }
}

function saveStoredSession(session: StoredSession | null) {
  try {
    if (session) {
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
    } else {
      localStorage.removeItem(AUTH_STORAGE_KEY);
    }
  } catch {
    // ignore quota errors
  }
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const initialSession = loadStoredSession();
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => !!initialSession);
  const [role, setRole] = useState<UserRole>(() => initialSession?.role || "employee");
  const [username, setUsername] = useState<string>(() => initialSession?.username || "Сотрудник ЦДО");
  const [token, setToken] = useState<string | null>(() => initialSession?.token || null);
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

  const login = useCallback(
    async (credentials: { role?: UserRole; username: string; password?: string }) => {
      setIsSwitchingRole(true);
      try {
        const cleanUser = credentials.username.trim() || "demo";
        const targetRole: UserRole = credentials.role || (cleanUser.toLowerCase() === "admin" ? "admin" : "employee");
        const res = await issueRoleToken(targetRole, cleanUser, credentials.password);
        const resolvedRole = (res.role as UserRole) || targetRole;
        setRole(resolvedRole);
        setUsername(res.username);
        setToken(res.access_token);
        setIsAuthenticated(true);
        saveStoredSession({
          token: res.access_token,
          role: resolvedRole,
          username: res.username,
        });
      } catch (err: any) {
        if (err?.status === 401) {
          throw new Error(err?.message || "Неверный логин или пароль. Тестовый доступ: demo / demo");
        }
        // Graceful offline demo fallback if backend is unreachable
        if (err?.name === "TypeError" || !err?.status) {
          const cleanUser = credentials.username.trim() || "demo";
          const fallbackRole: UserRole = credentials.role || (cleanUser.toLowerCase() === "admin" ? "admin" : "employee");
          const dummyToken = "offline-demo-token";
          setRole(fallbackRole);
          setUsername(cleanUser);
          setToken(dummyToken);
          setIsAuthenticated(true);
          saveStoredSession({
            token: dummyToken,
            role: fallbackRole,
            username: cleanUser,
          });
          return;
        }
        throw err;
      } finally {
        setIsSwitchingRole(false);
      }
    },
    []
  );

  const logout = useCallback(() => {
    saveStoredSession(null);
    setToken(null);
    setIsAuthenticated(false);
    setRole("employee");
    setUsername("Сотрудник ЦДО");
  }, []);

  const switchRole = useCallback(
    async (targetRole: UserRole, password?: string) => {
      setIsSwitchingRole(true);
      try {
        const roleMeta = ROLE_METADATA[targetRole];
        const baseName = username.trim() || roleMeta.shortLabel;
        const finalPassword =
          password !== undefined
            ? password
            : targetRole === "admin"
            ? "cdo-admin-2026"
            : undefined;
        const res = await issueRoleToken(targetRole, baseName, finalPassword);
        setRole(targetRole);
        setUsername(res.username);
        setToken(res.access_token);
        saveStoredSession({
          token: res.access_token,
          role: targetRole,
          username: res.username,
        });
      } catch (err: any) {
        if (err?.status === 401) {
          setIsSwitchingRole(false);
          alert("Для переключения на роль Администратора требуется пароль (cdo-admin-2026)");
          return;
        }
        // Fallback if backend is warming up or offline
        setRole(targetRole);
        const fallbackName = `Демо (${ROLE_METADATA[targetRole].shortLabel})`;
        setUsername(fallbackName);
        saveStoredSession({
          token: token || "offline-token",
          role: targetRole,
          username: fallbackName,
        });
      } finally {
        setIsSwitchingRole(false);
      }
    },
    [username, token]
  );

  useEffect(() => {
    void refreshHealth();
    const timer = setInterval(() => {
      void refreshHealth();
    }, 15000);
    return () => clearInterval(timer);
  }, [refreshHealth]);

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        role,
        username,
        token,
        health,
        isSwitchingRole,
        login,
        logout,
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

import React, { useState } from "react";
import { Check, ChevronDown, Shield } from "lucide-react";
import { ROLE_METADATA, useAuth } from "../../context/AuthContext";
import { ScreenId, UserRole } from "../../types/api";

interface HeaderProps {
  activeScreen: ScreenId;
  onSelectScreen: (screen: ScreenId) => void;
}

const ROLE_ORDER: UserRole[] = ["employee", "dou_specialist", "security_auditor", "admin"];

export const Header: React.FC<HeaderProps> = ({ activeScreen, onSelectScreen }) => {
  const { role, health, isSwitchingRole, switchRole } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const currentRoleMeta = ROLE_METADATA[role];
  const systemOnline = health?.db_connected !== false;

  return (
    <header className="h-16 px-6 border-b border-white/[0.08] bg-[#08080A] flex items-center justify-between shrink-0 z-10">
      {/* Left: System & Active Edition Pill */}
      <div className="flex items-center gap-3">
        <div className="inline-flex items-center gap-2.5 px-4 py-2 rounded-full bg-[#111115] border border-white/[0.12] text-sm font-medium text-white">
          <span
            className={`w-2 h-2 rounded-full ${
              systemOnline ? "bg-white" : "bg-[#C50337]"
            }`}
          />
          <span>Инструкция № ОД-184</span>
          <span className="text-zinc-500">•</span>
          <span className="font-mono text-zinc-300">
            Ред. {health?.active_version || "1.0"}
          </span>
        </div>

        <span className="hidden xl:inline-block text-xs text-zinc-400">
          PostgreSQL 16 + Локальная модель Qwen 2.5
        </span>
      </div>

      {/* Center: Strict Monochrome + Crimson Segmented Navigation */}
      <div className="hidden md:flex items-center gap-1 p-1 rounded-full bg-[#111115] border border-white/[0.1] text-sm">
        {(
          [
            { id: "assistant", label: "Диалог" },
            { id: "constructor", label: "Конструктор (7)" },
            { id: "compliance", label: "Нормоконтроль" },
            { id: "governance", label: "Версии и Аудит" },
          ] as Array<{ id: ScreenId; label: string }>
        ).map((tab) => (
          <button
            key={tab.id}
            onClick={() => onSelectScreen(tab.id)}
            className={`px-4 py-1.5 rounded-full font-medium transition ${
              activeScreen === tab.id
                ? "bg-[#C50337] text-white"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Right: 1-Click Role Switcher & OpenAPI Link */}
      <div className="flex items-center gap-3 relative">
        <div className="relative">
          <button
            disabled={isSwitchingRole}
            onClick={() => setDropdownOpen((o) => !o)}
            className="inline-flex items-center gap-2.5 px-4 py-2 rounded-full bg-[#111115] hover:bg-white/[0.08] border border-white/[0.14] text-sm font-medium text-white transition"
          >
            <Shield className="w-4 h-4 text-[#C50337]" />
            <span>Роль: {currentRoleMeta.shortLabel}</span>
            <ChevronDown className="w-4 h-4 text-zinc-400" />
          </button>

          {dropdownOpen && (
            <div className="absolute right-0 mt-2 w-80 rounded-2xl bg-[#111115] border border-white/[0.16] shadow-2xl p-2.5 z-50 space-y-1">
              <div className="px-3 py-2 border-b border-white/[0.08] flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                  Переключение роли (JWT RBAC)
                </span>
                <span className="text-xs font-mono text-zinc-400">HS256</span>
              </div>
              {ROLE_ORDER.map((r) => {
                const m = ROLE_METADATA[r];
                const isSelected = r === role;
                return (
                  <button
                    key={r}
                    onClick={() => {
                      void switchRole(r);
                      setDropdownOpen(false);
                    }}
                    className={`w-full text-left p-3 rounded-xl transition flex items-start justify-between gap-2 ${
                      isSelected
                        ? "bg-white/[0.09] border border-white/[0.2]"
                        : "hover:bg-white/[0.04] border border-transparent"
                    }`}
                  >
                    <div>
                      <div className="text-sm font-semibold text-white flex items-center gap-2">
                        <span>{m.label}</span>
                      </div>
                      <div className="text-xs text-zinc-400 mt-1">{m.description}</div>
                    </div>
                    {isSelected && <Check className="w-4 h-4 text-[#C50337] shrink-0 mt-1" />}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <a
          href="/docs"
          target="_blank"
          rel="noreferrer"
          className="hidden sm:inline-flex items-center px-4 py-2 rounded-full bg-[#111115] hover:bg-white/[0.08] border border-white/[0.12] text-sm font-medium text-zinc-200 transition"
        >
          API Docs
        </a>
      </div>
    </header>
  );
};

import React, { useState } from "react";
import { Check, ChevronDown, Shield } from "lucide-react";
import { ROLE_METADATA, useAuth } from "../../context/AuthContext";
import { ScreenId, UserRole } from "../../types/api";

interface HeaderProps {
  activeScreen: ScreenId;
  onSelectScreen: (screen: ScreenId) => void;
}

const ROLE_ORDER: UserRole[] = ["employee", "dou_specialist", "security_auditor", "admin"];

const SCREEN_TITLES: Record<ScreenId, string> = {
  assistant: "Консультант ДОУ",
  constructor: "Шаблоны документов",
  compliance: "Нормоконтроль .DOCX",
  matrix: "Матрица визирования",
  governance: "База знаний и Аудит",
};

export const Header: React.FC<HeaderProps> = ({ activeScreen }) => {
  const { role, health, isSwitchingRole, switchRole } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const currentRoleMeta = ROLE_METADATA[role];
  const systemOnline = health?.db_connected !== false;

  return (
    <header className="h-16 px-8 border-b border-white/[0.08] bg-[#08080A] flex items-center justify-between shrink-0 z-10">
      {/* Left: Current Section Title + Active Edition */}
      <div className="flex items-center gap-4">
        <h2 className="text-base font-semibold text-white">{SCREEN_TITLES[activeScreen]}</h2>
        <span className="text-zinc-600">•</span>
        <div className="inline-flex items-center gap-2 text-xs text-zinc-400">
          <span
            className={`w-2 h-2 rounded-full ${
              systemOnline ? "bg-white" : "bg-[#C50337]"
            }`}
          />
          <span>ОД-184 ред. {health?.active_version || "1.0"}</span>
        </div>
      </div>

      {/* Right: Clean Role Selector */}
      <div className="relative">
        <button
          disabled={isSwitchingRole}
          onClick={() => setDropdownOpen((o) => !o)}
          className="inline-flex items-center gap-2.5 px-4 py-2 rounded-full bg-[#111115] hover:bg-white/[0.06] border border-white/[0.12] text-sm font-medium text-white transition"
        >
          <Shield className="w-4 h-4 text-[#C50337]" />
          <span>{currentRoleMeta.shortLabel}</span>
          <ChevronDown className="w-4 h-4 text-zinc-400" />
        </button>

        {dropdownOpen && (
          <div className="absolute right-0 mt-2 w-72 rounded-2xl bg-[#111115] border border-white/[0.14] shadow-2xl p-2 z-50 space-y-1">
            <div className="px-3 py-2 border-b border-white/[0.08] text-xs font-medium text-zinc-400">
              Переключение роли (RBAC)
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
                  className={`w-full text-left p-2.5 rounded-xl transition flex items-center justify-between gap-2 ${
                    isSelected
                      ? "bg-white/[0.08] text-white"
                      : "hover:bg-white/[0.04] text-zinc-300"
                  }`}
                >
                  <div>
                    <div className="text-sm font-medium text-white">{m.label}</div>
                    <div className="text-xs text-zinc-500">{m.clearance}</div>
                  </div>
                  {isSelected && <Check className="w-4 h-4 text-[#C50337] shrink-0" />}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </header>
  );
};

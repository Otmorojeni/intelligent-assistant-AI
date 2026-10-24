import React from "react";
import {
  BookOpen,
  FileCheck2,
  FileSpreadsheet,
  FolderGit2,
  Layers,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Shield,
} from "lucide-react";
import { ScreenId, UserRole } from "../../types/api";
import { ROLE_METADATA, useAuth } from "../../context/AuthContext";

interface SidebarProps {
  activeScreen: ScreenId;
  onSelectScreen: (screen: ScreenId) => void;
  onNewChat: () => void;
  onQuickTemplateSelect: (moduleCode: string) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

const QUICK_MODULES = [
  { code: "MOD-ORDER-IS", reg: "УТВ-01", title: "Ввод ИС в эксплуатацию" },
  { code: "MOD-ORDER-DOU", reg: "УТВ-02", title: "Ответственные за ДОУ" },
  { code: "MOD-ORDER-PROP", reg: "УТВ-03", title: "Прием-передача дел" },
  { code: "MOD-ORDER-LNA", reg: "УТВ-04", title: "Утверждение ЛНА" },
  { code: "MOD-DISP-PROJECT", reg: "УТВ-06", title: "Проектный комитет" },
];

export const Sidebar: React.FC<SidebarProps> = ({
  activeScreen,
  onSelectScreen,
  onNewChat,
  onQuickTemplateSelect,
  collapsed,
  onToggleCollapse,
}) => {
  const { role, switchRole } = useAuth();
  const roleInfo = ROLE_METADATA[role];

  const nextRoleMap: Record<UserRole, UserRole> = {
    employee: "dou_specialist",
    dou_specialist: "security_auditor",
    security_auditor: "admin",
    admin: "employee",
  };

  return (
    <aside
      className={`${
        collapsed ? "w-20" : "w-72"
      } h-screen bg-[#08080A] border-r border-white/[0.08] flex flex-col justify-between transition-all duration-200 select-none shrink-0 z-20`}
    >
      {/* Top section */}
      <div className="p-5 space-y-6 overflow-y-auto">
        {/* Brand Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="w-9 h-9 rounded-lg bg-[#C50337] flex items-center justify-center font-bold text-sm text-white shrink-0 tracking-tight">
              ЦБ
            </div>
            {!collapsed && (
              <div className="truncate">
                <div className="text-base font-semibold tracking-tight text-white">
                  ЦДО Ассистент
                </div>
                <div className="text-xs text-zinc-400 truncate">Банк России • ОД-184</div>
              </div>
            )}
          </div>
          <button
            onClick={onToggleCollapse}
            title={collapsed ? "Развернуть меню" : "Свернуть меню"}
            className="p-2 rounded-lg text-zinc-400 hover:text-white hover:bg-white/[0.06] transition"
          >
            {collapsed ? <PanelLeftOpen className="w-5 h-5" /> : <PanelLeftClose className="w-5 h-5" />}
          </button>
        </div>

        {/* New Chat Button */}
        <button
          onClick={() => {
            onSelectScreen("assistant");
            onNewChat();
          }}
          className="w-full py-3 px-4 rounded-xl bg-white/[0.06] hover:bg-white/[0.11] border border-white/[0.12] text-sm font-medium text-white flex items-center justify-center sm:justify-start gap-3 transition"
        >
          <MessageSquarePlus className="w-4 h-4 text-zinc-300 shrink-0" />
          {!collapsed && <span>Новый диалог</span>}
        </button>

        {/* Main Navigation */}
        <div className="space-y-1.5">
          {!collapsed && (
            <div className="px-2 pb-1.5 text-xs font-medium text-zinc-500 uppercase tracking-wider">
              Рабочие разделы
            </div>
          )}

          {(
            [
              { id: "assistant", label: "Консультант ДОУ", icon: BookOpen },
              { id: "constructor", label: "Шаблоны документов", icon: FileSpreadsheet },
              { id: "compliance", label: "Нормоконтроль .DOCX", icon: FileCheck2 },
              { id: "governance", label: "Реестр версий и ИБ", icon: FolderGit2 },
            ] as Array<{ id: ScreenId; label: string; icon: React.FC<{ className?: string }> }>
          ).map((item) => {
            const Icon = item.icon;
            const isActive = activeScreen === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectScreen(item.id)}
                className={`w-full flex items-center gap-3 px-3.5 py-3 rounded-xl text-sm font-medium transition ${
                  isActive
                    ? "bg-[#C50337] text-white shadow-sm"
                    : "text-zinc-400 hover:text-white hover:bg-white/[0.04]"
                }`}
              >
                <Icon className={`w-4 h-4 shrink-0 ${isActive ? "text-white" : "text-zinc-400"}`} />
                {!collapsed && <span>{item.label}</span>}
              </button>
            );
          })}
        </div>

        {/* Modular Templates Quick List */}
        {!collapsed && (
          <div className="space-y-1.5 pt-4 border-t border-white/[0.08]">
            <div className="px-2 pb-1.5 text-xs font-medium text-zinc-500 uppercase tracking-wider flex items-center justify-between">
              <span>Модули УТВ-01..07</span>
              <Layers className="w-3.5 h-3.5 text-zinc-500" />
            </div>
            {QUICK_MODULES.map((mod) => (
              <button
                key={mod.code}
                onClick={() => {
                  onQuickTemplateSelect(mod.code);
                  onSelectScreen("constructor");
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-zinc-400 hover:text-white hover:bg-white/[0.04] transition text-left"
              >
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-white/[0.06] text-zinc-300 shrink-0">
                  {mod.reg}
                </span>
                <span className="truncate">{mod.title}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Bottom Security Card */}
      <div className="p-4 border-t border-white/[0.08]">
        {!collapsed ? (
          <div className="p-4 rounded-xl bg-[#111115] border border-white/[0.1] space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-zinc-400">Контур доступа</span>
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-white/[0.07] text-zinc-200">
                {roleInfo.clearance}
              </span>
            </div>

            <div>
              <div className="text-sm font-semibold text-white">{roleInfo.label}</div>
              <p className="text-xs text-zinc-400 leading-relaxed mt-1">
                {roleInfo.description}
              </p>
            </div>

            <button
              onClick={() => void switchRole(nextRoleMap[role])}
              className="w-full py-2.5 px-3 rounded-lg bg-white/[0.08] hover:bg-white/[0.14] border border-white/[0.12] text-xs font-semibold text-white transition flex items-center justify-center gap-2"
            >
              <Shield className="w-4 h-4 text-zinc-300" />
              <span>Сменить роль →</span>
            </button>
          </div>
        ) : (
          <button
            onClick={() => void switchRole(nextRoleMap[role])}
            title={`Текущая роль: ${roleInfo.label}`}
            className="w-full p-3 rounded-xl bg-white/[0.08] hover:bg-white/[0.15] flex items-center justify-center text-white"
          >
            <Shield className="w-5 h-5" />
          </button>
        )}
      </div>
    </aside>
  );
};

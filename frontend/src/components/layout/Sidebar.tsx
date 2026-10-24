import React, { useState } from "react";
import {
  BookOpen,
  Check,
  ChevronDown,
  FileCheck2,
  FileSpreadsheet,
  FolderGit2,
  GitMerge,
  MessageSquare,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Shield,
  Trash2,
} from "lucide-react";
import { ChatSessionRecord, ScreenId, UserRole } from "../../types/api";
import { ROLE_METADATA, useAuth } from "../../context/AuthContext";

interface SidebarProps {
  activeScreen: ScreenId;
  onSelectScreen: (screen: ScreenId) => void;
  onNewChat: () => void;
  sessions: ChatSessionRecord[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

const ROLE_ORDER: UserRole[] = ["employee", "dou_specialist", "security_auditor", "admin"];

const NAV_GROUPS: Array<{
  groupTitle: string;
  items: Array<{ id: ScreenId; label: string; icon: React.FC<{ className?: string }> }>;
}> = [
  {
    groupTitle: "Работа с документами",
    items: [
      { id: "assistant", label: "Диалог с ИИ", icon: BookOpen },
      { id: "constructor", label: "Шаблоны документов", icon: FileSpreadsheet },
      { id: "compliance", label: "Проверка документа", icon: FileCheck2 },
    ],
  },
  {
    groupTitle: "Справочники и управление",
    items: [
      { id: "matrix", label: "Маршруты согласования", icon: GitMerge },
      { id: "governance", label: "Документы и история", icon: FolderGit2 },
    ],
  },
];

/**
 * Custom Brand Emblem for "DoCorp"
 */
const DoCorpLogo: React.FC<{ className?: string }> = ({ className = "w-16 h-16" }) => (
  <img
    src="/docorp-logo.png"
    alt="DoCorp"
    className={`${className} shrink-0 object-contain select-none`}
  />
);

export const Sidebar: React.FC<SidebarProps> = ({
  activeScreen,
  onSelectScreen,
  onNewChat,
  sessions,
  activeSessionId,
  onSelectSession,
  onDeleteSession,
  collapsed,
  onToggleCollapse,
}) => {
  const { role, isSwitchingRole, switchRole } = useAuth();
  const [roleDropdownOpen, setRoleDropdownOpen] = useState(false);

  const currentRoleMeta = ROLE_METADATA[role];
  const historyList = sessions.filter((s) => s.turns.length > 0);

  return (
    <aside
      className="h-screen bg-[#08080A] border-r border-white/[0.1] flex flex-col justify-between transition-all duration-200 select-none shrink-0 z-20"
      style={{ width: collapsed ? "5.25rem" : "20rem" }}
    >
      {/* Top & Scrollable Center */}
      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        {/* Brand Header */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-3.5 overflow-hidden">
            <DoCorpLogo className={collapsed ? "w-12 h-12" : "w-16 h-16"} />
            {!collapsed && (
              <div className="min-w-0">
                <div className="flex items-center leading-none">
                  <span className="text-2xl font-bold tracking-tight text-white">Do</span>
                  <span className="text-2xl font-bold tracking-tight text-[#C50337]">Corp</span>
                </div>
              </div>
            )}
          </div>
          <button
            onClick={onToggleCollapse}
            title={collapsed ? "Развернуть" : "Свернуть"}
            className="p-2 rounded-lg text-zinc-300 hover:text-white hover:bg-white/[0.08] transition shrink-0"
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
          className="w-full py-3 px-4 rounded-xl bg-white/[0.07] hover:bg-white/[0.12] border border-white/[0.14] text-base font-semibold text-white flex items-center justify-center sm:justify-start gap-3 transition"
        >
          <MessageSquarePlus className="w-5 h-5 text-zinc-200 shrink-0" />
          {!collapsed && <span>Новый диалог</span>}
        </button>

        {/* Grouped Navigation */}
        <div className="space-y-6">
          {NAV_GROUPS.map((group) => (
            <div key={group.groupTitle} className="space-y-1.5">
              {!collapsed && (
                <div className="px-2.5 pb-1 text-xs font-semibold text-zinc-400 uppercase tracking-wider">
                  {group.groupTitle}
                </div>
              )}
              {group.items.map((item) => {
                const Icon = item.icon;
                const isActive = activeScreen === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onSelectScreen(item.id)}
                    className={`w-full flex items-center gap-3.5 px-3.5 py-3 rounded-xl text-base font-medium transition ${
                      isActive
                        ? "bg-[#C50337] text-white font-semibold shadow-sm"
                        : "text-zinc-200 hover:text-white hover:bg-white/[0.06]"
                    }`}
                  >
                    <Icon className="w-5 h-5 shrink-0" />
                    {!collapsed && <span>{item.label}</span>}
                  </button>
                );
              })}
            </div>
          ))}
        </div>

        {/* Chat History List */}
        {!collapsed && (
          <div className="space-y-2 pt-3 border-t border-white/[0.09]">
            <div className="px-2.5 pb-1 text-xs font-semibold text-zinc-400 uppercase tracking-wider">
              История чатов
            </div>

            {historyList.length === 0 ? (
              <div className="px-2.5 py-2 text-sm text-zinc-500">Пока нет сохраненных чатов</div>
            ) : (
              <div className="space-y-1.5">
                {historyList.map((sess) => {
                  const isCurrent = sess.id === activeSessionId && activeScreen === "assistant";
                  return (
                    <div
                      key={sess.id}
                      className={`group flex items-center justify-between gap-2 px-3 py-2.5 rounded-xl text-sm transition cursor-pointer ${
                        isCurrent
                          ? "bg-white/[0.1] text-white font-semibold"
                          : "text-zinc-200 hover:text-white hover:bg-white/[0.05] font-medium"
                      }`}
                      onClick={() => {
                        onSelectSession(sess.id);
                        onSelectScreen("assistant");
                      }}
                    >
                      <div className="flex items-center gap-2.5 truncate">
                        <MessageSquare className="w-4 h-4 text-zinc-400 shrink-0" />
                        <span className="truncate">{sess.title}</span>
                      </div>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeleteSession(sess.id);
                        }}
                        title="Удалить диалог"
                        className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-white/[0.12] text-zinc-300 hover:text-white transition shrink-0"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bottom User Role Switcher Pill */}
      <div className="p-4 border-t border-white/[0.1] relative">
        {roleDropdownOpen && !collapsed && (
          <div className="absolute bottom-20 left-4 right-4 rounded-2xl bg-[#111115] border border-white/[0.16] shadow-2xl p-2.5 z-50 space-y-1">
            <div className="px-3 py-1.5 border-b border-white/[0.08] text-xs font-semibold text-zinc-300">
              Смена пользователя
            </div>
            {ROLE_ORDER.map((r) => {
              const m = ROLE_METADATA[r];
              const isSelected = r === role;
              return (
                <button
                  key={r}
                  onClick={() => {
                    void switchRole(r);
                    setRoleDropdownOpen(false);
                  }}
                  className={`w-full text-left p-2.5 rounded-xl transition flex items-center justify-between gap-2 ${
                    isSelected
                      ? "bg-white/[0.1] text-white"
                      : "hover:bg-white/[0.05] text-zinc-200"
                  }`}
                >
                  <div className="truncate">
                    <div className="text-sm font-semibold text-white truncate">{m.shortLabel}</div>
                    <div className="text-xs text-zinc-400 truncate">{m.clearance}</div>
                  </div>
                  {isSelected && <Check className="w-4 h-4 text-[#C50337] shrink-0" />}
                </button>
              );
            })}
          </div>
        )}

        <button
          disabled={isSwitchingRole}
          onClick={() => {
            if (collapsed) {
              const nextIdx = (ROLE_ORDER.indexOf(role) + 1) % ROLE_ORDER.length;
              void switchRole(ROLE_ORDER[nextIdx]);
            } else {
              setRoleDropdownOpen((o) => !o);
            }
          }}
          className="w-full inline-flex items-center justify-between gap-3 px-4 py-3 rounded-full bg-[#111115] hover:bg-white/[0.07] border border-white/[0.16] text-base font-semibold text-white transition"
        >
          <div className="flex items-center gap-2.5 truncate">
            <Shield className="w-4 h-4 text-[#C50337] shrink-0" />
            {!collapsed && <span className="truncate">{currentRoleMeta.shortLabel}</span>}
          </div>
          {!collapsed && <ChevronDown className="w-4 h-4 text-zinc-300 shrink-0" />}
        </button>
      </div>
    </aside>
  );
};

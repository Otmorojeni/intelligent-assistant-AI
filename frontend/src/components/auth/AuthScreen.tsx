import React, { useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Lock,
  Shield,
  Sparkles,
  User,
} from "lucide-react";
import { ROLE_METADATA, useAuth } from "../../context/AuthContext";
import { UserRole } from "../../types/api";

const ROLE_OPTIONS: UserRole[] = ["employee", "dou_specialist", "security_auditor", "admin"];

const ROLE_PRESETS: Record<UserRole, { name: string; dept: string }> = {
  employee: {
    name: "Иванов И.И.",
    dept: "Департамент логистики",
  },
  dou_specialist: {
    name: "Петрова А.С.",
    dept: "Департамент ДОУ",
  },
  security_auditor: {
    name: "Соколов М.А.",
    dept: "Служба информационной безопасности",
  },
  admin: {
    name: "Администратор системы",
    dept: "Центр управления ДОУ",
  },
};

export const AuthScreen: React.FC = () => {
  const { login, health } = useAuth();
  const [selectedRole, setSelectedRole] = useState<UserRole>("employee");
  const [usernameInput, setUsernameInput] = useState<string>(ROLE_PRESETS.employee.name);
  const [passwordInput, setPasswordInput] = useState<string>("");
  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const currentMeta = ROLE_METADATA[selectedRole];
  const isOnline = health?.db_connected !== false;

  const handleSelectRole = (r: UserRole) => {
    setSelectedRole(r);
    setUsernameInput(ROLE_PRESETS[r].name);
    setErrorMessage(null);
    if (r === "admin" && !passwordInput) {
      setPasswordInput("cdo-admin-2026");
    }
  };

  const handleLoginSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setErrorMessage(null);
    setIsSubmitting(true);

    try {
      await login({
        role: selectedRole,
        username: usernameInput.trim() || ROLE_PRESETS[selectedRole].name,
        password: selectedRole === "admin" ? passwordInput : undefined,
      });
    } catch (err: any) {
      setErrorMessage(
        err?.message || "Не удалось выполнить авторизацию. Проверьте введенные данные."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleQuickDemoLogin = async (role: UserRole) => {
    setSelectedRole(role);
    setUsernameInput(ROLE_PRESETS[role].name);
    setErrorMessage(null);
    setIsSubmitting(true);

    try {
      await login({
        role,
        username: ROLE_PRESETS[role].name,
        password: role === "admin" ? "cdo-admin-2026" : undefined,
      });
    } catch (err: any) {
      setErrorMessage(
        err?.message || "Ошибка быстрого входа. Попробуйте еще раз."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen w-screen zyricon-stage-bg flex items-center justify-center p-4 sm:p-6 md:p-10 select-none overflow-y-auto">
      <div className="w-full max-w-2xl my-auto space-y-6">
        {/* Brand Header */}
        <div className="text-center space-y-3">
          <div className="inline-flex items-center gap-3 justify-center">
            <img
              src="/docorp-logo.png"
              alt="DoCorp"
              className="w-14 h-14 sm:w-16 sm:h-16 object-contain drop-shadow-[0_0_20px_rgba(197,3,55,0.45)]"
            />
            <div className="text-left">
              <div className="flex items-center text-3xl font-extrabold tracking-tight">
                <span className="text-white">Do</span>
                <span className="text-[#C50337]">Corp</span>
              </div>
              <div className="text-xs uppercase tracking-widest text-zinc-400 font-semibold">
                AI Assistant • ОД-184
              </div>
            </div>
          </div>
          <p className="text-sm text-zinc-300 max-w-lg mx-auto">
            Единая корпоративная система делопроизводства, нормативного контроля и маршрутизации согласования документов
          </p>
        </div>

        {/* Auth Glass Card */}
        <div className="zyricon-glass-card rounded-3xl p-6 sm:p-8 space-y-6 border border-white/[0.14] shadow-2xl backdrop-blur-2xl">
          <div className="flex items-center justify-between border-b border-white/[0.08] pb-4">
            <div>
              <h2 className="text-lg font-semibold text-white">Авторизация в системе</h2>
              <p className="text-xs text-zinc-400 mt-0.5">
                Выберите профиль и подтвердите учетные данные для начала работы
              </p>
            </div>
            <div className="hidden sm:inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/[0.04] border border-white/[0.08] text-xs text-zinc-300">
              <span
                className={`w-2 h-2 rounded-full ${
                  isOnline ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.7)]" : "bg-amber-400"
                }`}
              />
              <span>{isOnline ? "Сервер в сети" : "Сервис ожидает связи"}</span>
            </div>
          </div>

          {/* Role Selection Grid */}
          <div className="space-y-2">
            <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider">
              1. Выберите роль пользователя (RBAC)
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {ROLE_OPTIONS.map((r) => {
                const meta = ROLE_METADATA[r];
                const isSelected = r === selectedRole;
                return (
                  <button
                    key={r}
                    type="button"
                    onClick={() => handleSelectRole(r)}
                    className={`text-left p-3.5 rounded-2xl border transition-all duration-150 flex flex-col justify-between gap-2 ${
                      isSelected
                        ? "bg-white/[0.09] border-[#C50337] ring-1 ring-[#C50337] shadow-[0_0_20px_rgba(197,3,55,0.25)]"
                        : "bg-[#0D0D11] border-white/[0.08] hover:border-white/20 hover:bg-white/[0.03]"
                    }`}
                  >
                    <div className="flex items-center justify-between w-full">
                      <div className="flex items-center gap-2">
                        <Shield
                          className={`w-4 h-4 ${
                            isSelected ? "text-[#C50337]" : "text-zinc-400"
                          }`}
                        />
                        <span className="text-sm font-semibold text-white">
                          {meta.shortLabel}
                        </span>
                      </div>
                      <span className={`text-[11px] px-2 py-0.5 rounded-full border ${meta.badgeColor}`}>
                        {meta.clearance}
                      </span>
                    </div>
                    <p className="text-xs text-zinc-400 line-clamp-2">
                      {meta.description}
                    </p>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Form Credentials */}
          <form onSubmit={handleLoginSubmit} className="space-y-4 pt-1">
            <div className="space-y-3">
              <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider">
                2. Учетные данные пользователя
              </label>

              {/* Username Input */}
              <div className="space-y-1.5">
                <label className="text-xs text-zinc-400 flex items-center gap-1.5">
                  <User className="w-3.5 h-3.5 text-zinc-400" />
                  <span>ФИО / Название учетной записи</span>
                </label>
                <input
                  type="text"
                  required
                  value={usernameInput}
                  onChange={(e) => setUsernameInput(e.target.value)}
                  placeholder="Например, Иванов И.И."
                  className="w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-[#C50337] focus:ring-1 focus:ring-[#C50337] transition"
                />
              </div>

              {/* Password Input for Admin */}
              {selectedRole === "admin" && (
                <div className="space-y-1.5 animate-in fade-in duration-200">
                  <div className="flex items-center justify-between">
                    <label className="text-xs text-zinc-400 flex items-center gap-1.5">
                      <Lock className="w-3.5 h-3.5 text-zinc-400" />
                      <span>Пароль администратора (Обязательно для роли admin)</span>
                    </label>
                    <button
                      type="button"
                      onClick={() => setPasswordInput("cdo-admin-2026")}
                      className="text-xs text-[#C50337] hover:underline flex items-center gap-1"
                    >
                      <KeyRound className="w-3 h-3" />
                      <span>Вставить демо-пароль</span>
                    </button>
                  </div>
                  <div className="relative">
                    <input
                      type={showPassword ? "text" : "password"}
                      required
                      value={passwordInput}
                      onChange={(e) => setPasswordInput(e.target.value)}
                      placeholder="Введите пароль администратора"
                      className="w-full pl-3.5 pr-10 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-[#C50337] focus:ring-1 focus:ring-[#C50337] transition"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((p) => !p)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white transition"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <p className="text-[11px] text-zinc-400">
                    Подсказка для демо-доступа: <code className="text-rose-300 font-mono">cdo-admin-2026</code>
                  </p>
                </div>
              )}
            </div>

            {/* Error Message Alert */}
            {errorMessage && (
              <div className="p-3.5 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-200 text-xs flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-[#C50337] shrink-0 mt-0.5" />
                <span className="flex-1 leading-relaxed">{errorMessage}</span>
              </div>
            )}

            {/* Main Submit Button */}
            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full py-3.5 px-5 rounded-xl bg-[#C50337] hover:bg-[#a6022e] active:scale-[0.99] text-white font-semibold text-sm flex items-center justify-center gap-2 shadow-[0_0_25px_rgba(197,3,55,0.4)] transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isSubmitting ? (
                <>
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Авторизация...</span>
                </>
              ) : (
                <>
                  <span>Войти как {currentMeta.shortLabel}</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          {/* Quick 1-Click Demo Login Bar */}
          <div className="pt-2 border-t border-white/[0.08] space-y-2.5">
            <div className="flex items-center gap-1.5 text-xs text-zinc-400">
              <Sparkles className="w-3.5 h-3.5 text-[#C50337]" />
              <span className="font-semibold text-zinc-300">Быстрый демо-вход в 1 клик:</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {ROLE_OPTIONS.map((r) => (
                <button
                  key={r}
                  type="button"
                  disabled={isSubmitting}
                  onClick={() => handleQuickDemoLogin(r)}
                  className="py-2 px-2.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs text-zinc-200 font-medium text-center truncate transition disabled:opacity-50"
                  title={`Войти как ${ROLE_METADATA[r].shortLabel}`}
                >
                  {ROLE_METADATA[r].shortLabel}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Footer Info Badges */}
        <div className="text-center text-xs text-zinc-400 space-y-1">
          <p>
            Инструкция по делопроизводству ОД-184 ред. 2.0 • Защищенный доступ Bearer JWT
          </p>
          <p className="text-[11px] text-zinc-400">
            После входа вы сможете свободно переключать роли и тестировать все сценарии в боковом меню
          </p>
        </div>
      </div>
    </div>
  );
};

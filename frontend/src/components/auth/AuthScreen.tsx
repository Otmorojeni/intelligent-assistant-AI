import React, { useState } from "react";
import { AlertCircle, Eye, EyeOff, Lock, User } from "lucide-react";
import { useAuth } from "../../context/AuthContext";

export const AuthScreen: React.FC = () => {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) return;

    setErrorMessage(null);
    setIsSubmitting(true);

    try {
      await login({
        username: username.trim(),
        password: password,
      });
    } catch (err: any) {
      setErrorMessage(err?.message || "Неверный логин или пароль");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen w-screen flex items-center justify-center p-4 bg-[#08080A] text-zinc-100 relative overflow-hidden select-none">
      {/* Subtle radial crimson glow in background */}
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(197,3,55,0.09)_0%,transparent_70%)] pointer-events-none" />

      {/* Centered Minimalist Card */}
      <div className="relative w-full max-w-sm rounded-3xl bg-[#111116] border border-white/[0.14] p-8 shadow-2xl backdrop-blur-2xl space-y-6">
        {/* Brand & Heading */}
        <div className="flex flex-col items-center justify-center text-center space-y-3">
          <img
            src="/docorp-logo.png"
            alt="DoCorp"
            className="w-14 h-14 object-contain drop-shadow-[0_4px_16px_rgba(197,3,55,0.3)]"
          />
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Авторизация</h1>
            <p className="text-xs text-zinc-400 mt-1">Корпоративный ассистент ДОУ</p>
          </div>
        </div>

        {/* Error Alert */}
        {errorMessage && (
          <div className="p-3 rounded-xl bg-red-500/15 border border-red-500/30 text-xs text-red-300 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0 text-red-400" />
            <span className="flex-1">{errorMessage}</span>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-zinc-300 mb-1.5">Логин</label>
            <div className="relative">
              <User className="w-4 h-4 text-zinc-500 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Введите логин"
                autoComplete="username"
                autoFocus
                className="w-full pl-10 pr-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-white text-sm placeholder-zinc-500 focus:outline-none focus:border-[#C50337] focus:ring-1 focus:ring-[#C50337] transition"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-zinc-300 mb-1.5">Пароль</label>
            <div className="relative">
              <Lock className="w-4 h-4 text-zinc-500 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type={showPassword ? "text" : "password"}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Введите пароль"
                autoComplete="current-password"
                className="w-full pl-10 pr-10 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-white text-sm placeholder-zinc-500 focus:outline-none focus:border-[#C50337] focus:ring-1 focus:ring-[#C50337] transition"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                tabIndex={-1}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white transition"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Submit button */}
          <button
            type="submit"
            disabled={isSubmitting || !username.trim() || !password}
            className="w-full py-3 rounded-xl bg-[#C50337] hover:bg-[#a8022e] disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold text-sm transition shadow-lg shadow-[#C50337]/25 flex items-center justify-center gap-2"
          >
            {isSubmitting ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Вход...</span>
              </>
            ) : (
              <span>Войти</span>
            )}
          </button>
        </form>
      </div>
    </div>
  );
};

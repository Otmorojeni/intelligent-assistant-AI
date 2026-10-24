import React, { useCallback, useEffect, useRef, useState } from "react";
import { Check, ChevronDown, GitMerge, Search, X } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import {
  calculateApprovalRoute,
  fetchApprovalRules,
} from "../../services/apiClient";
import {
  ApprovalCalculateResponse,
  ApprovalRuleItem,
} from "../../types/api";

export const MatrixScreen: React.FC = () => {
  const { token } = useAuth();
  const [rules, setRules] = useState<ApprovalRuleItem[]>([]);
  const [calcDocType, setCalcDocType] = useState("Приказ о приеме и передаче дел и имущества");
  const [isRuleDropdownOpen, setIsRuleDropdownOpen] = useState(false);
  const [ruleSearchQuery, setRuleSearchQuery] = useState("");
  const ruleDropdownRef = useRef<HTMLDivElement>(null);

  const [usesModule, setUsesModule] = useState(true);
  const [involvesInfosec, setInvolvesInfosec] = useState(false);
  const [involvesIt, setInvolvesIt] = useState(false);
  const [involvesRegional, setInvolvesRegional] = useState(false);
  const [calcResult, setCalcResult] = useState<ApprovalCalculateResponse | null>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (ruleDropdownRef.current && !ruleDropdownRef.current.contains(event.target as Node)) {
        setIsRuleDropdownOpen(false);
      }
    }
    if (isRuleDropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isRuleDropdownOpen]);

  // Close dropdown on Escape key
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsRuleDropdownOpen(false);
      }
    }
    if (isRuleDropdownOpen) {
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isRuleDropdownOpen]);

  const loadRules = useCallback(async () => {
    try {
      const list = await fetchApprovalRules(token);
      setRules(list);
      if (list.length > 0) {
        setCalcDocType(list[0].doc_type_name);
      }
    } catch {
      // ignore
    }
  }, [token]);

  useEffect(() => {
    void loadRules();
  }, [loadRules]);

  const handleCalculateMatrix = async () => {
    try {
      const res = await calculateApprovalRoute(
        {
          doc_type: calcDocType,
          uses_module: usesModule,
          involves_infosec_access: involvesInfosec,
          involves_it: involvesIt,
          involves_regional: involvesRegional,
          initiator_department: "Департамент ДОУ",
        },
        token
      );
      setCalcResult(res);
    } catch {
      // ignore
    }
  };

  const currentRule = rules.find((r) => r.doc_type_name === calcDocType);

  const filteredRules = rules.filter((r) => {
    if (!ruleSearchQuery.trim()) return true;
    const q = ruleSearchQuery.toLowerCase().trim();
    return (
      r.rule_number.toString().includes(q) ||
      r.doc_type_name.toLowerCase().includes(q) ||
      (r.condition_description && r.condition_description.toLowerCase().includes(q))
    );
  });

  return (
    <div className="flex-1 h-screen zyricon-stage-bg overflow-y-auto px-6 sm:px-12 py-10">
      <div className="max-w-5xl mx-auto space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">Маршруты согласования документов</h1>
          <p className="text-sm text-zinc-400 mt-1">
            Быстрый подбор согласующих подразделений и таблица из 13 правил согласования
          </p>
        </div>

        {/* Route Calculator */}
        <div className="zyricon-glass-card rounded-2xl p-6 space-y-5">
          <div className="flex items-center gap-2.5">
            <GitMerge className="w-5 h-5 text-[#C50337]" />
            <h2 className="text-base font-semibold text-white">Подобрать маршрут согласования</h2>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-end">
            <div className="lg:col-span-5 relative" ref={ruleDropdownRef}>
              <div className="flex items-center justify-between text-xs text-zinc-400 mb-1.5">
                <span>Вид документа (Правила № 1–13)</span>
                {currentRule && (
                  <span className="text-[11px] text-zinc-400 font-mono">
                    Правило #{currentRule.rule_number}
                  </span>
                )}
              </div>

              {/* Custom Dropdown Trigger */}
              <button
                type="button"
                onClick={() => setIsRuleDropdownOpen((prev) => !prev)}
                className={`w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border text-left text-sm text-white flex items-center justify-between gap-2.5 transition select-none ${
                  isRuleDropdownOpen
                    ? "border-[#C50337] ring-1 ring-[#C50337]/50 shadow-[0_0_15px_rgba(197,3,55,0.25)]"
                    : "border-white/[0.14] hover:border-white/30"
                }`}
                aria-expanded={isRuleDropdownOpen}
                aria-haspopup="listbox"
              >
                <div className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden">
                  <span className="shrink-0 px-2 py-0.5 rounded-md bg-[#C50337]/20 border border-[#C50337]/40 text-xs font-semibold text-rose-300">
                    № {currentRule?.rule_number || "—"}
                  </span>
                  <span className="truncate font-medium text-white" title={calcDocType}>
                    {calcDocType}
                  </span>
                </div>
                <ChevronDown
                  className={`w-4 h-4 text-zinc-400 shrink-0 transition-transform duration-200 ${
                    isRuleDropdownOpen ? "rotate-180 text-white" : ""
                  }`}
                />
              </button>

              {/* Custom Dropdown Popover */}
              {isRuleDropdownOpen && (
                <div className="absolute left-0 right-0 top-full mt-2 z-50 rounded-xl bg-[#111115] border border-white/[0.18] shadow-2xl backdrop-blur-xl overflow-hidden flex flex-col max-h-80 w-full animate-in fade-in zoom-in-95 duration-150">
                  {/* Search header inside dropdown */}
                  <div className="p-2.5 border-b border-white/[0.08] bg-[#15151A] sticky top-0 z-10">
                    <div className="relative">
                      <Search className="w-3.5 h-3.5 text-zinc-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                      <input
                        type="text"
                        value={ruleSearchQuery}
                        onChange={(e) => setRuleSearchQuery(e.target.value)}
                        placeholder="Поиск по номеру или названию..."
                        className="w-full pl-8 pr-7 py-1.5 rounded-lg bg-[#0D0D11] border border-white/[0.12] text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-[#C50337]"
                        autoFocus
                      />
                      {ruleSearchQuery && (
                        <button
                          type="button"
                          onClick={() => setRuleSearchQuery("")}
                          className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white"
                          title="Очистить"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Scrollable rules list */}
                  <div className="overflow-y-auto divide-y divide-white/[0.04] p-1">
                    {filteredRules.length === 0 ? (
                      <div className="p-4 text-center text-xs text-zinc-400">
                        Правило не найдено
                      </div>
                    ) : (
                      filteredRules.map((r) => {
                        const isSelected = r.doc_type_name === calcDocType;
                        return (
                          <button
                            key={r.rule_number}
                            type="button"
                            onClick={() => {
                              setCalcDocType(r.doc_type_name);
                              setIsRuleDropdownOpen(false);
                              setRuleSearchQuery("");
                            }}
                            className={`w-full text-left px-3 py-2.5 rounded-lg transition flex items-start gap-2.5 ${
                              isSelected
                                ? "bg-[#C50337]/15 border border-[#C50337]/35 text-white"
                                : "hover:bg-white/[0.06] text-zinc-200 border border-transparent"
                            }`}
                          >
                            <span
                              className={`shrink-0 mt-0.5 px-1.5 py-0.5 rounded text-[11px] font-semibold ${
                                isSelected
                                  ? "bg-[#C50337] text-white"
                                  : "bg-white/[0.08] text-rose-300 border border-white/[0.1]"
                              }`}
                            >
                              № {r.rule_number}
                            </span>
                            <div className="flex-1 min-w-0">
                              <div className="text-xs sm:text-sm font-medium leading-snug break-words">
                                {r.doc_type_name}
                              </div>
                              {r.condition_description && (
                                <div className="text-[11px] text-zinc-400 mt-0.5 break-words line-clamp-2">
                                  {r.condition_description}
                                </div>
                              )}
                            </div>
                            {isSelected && (
                              <Check className="w-4 h-4 text-[#C50337] shrink-0 mt-0.5" />
                            )}
                          </button>
                        );
                      })
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="lg:col-span-5 flex flex-wrap gap-4 text-sm text-zinc-200 pb-1">
              <label className="inline-flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={usesModule}
                  onChange={(e) => setUsesModule(e.target.checked)}
                  className="rounded accent-[#C50337]"
                />
                <span>Модульный шаблон</span>
              </label>
              <label className="inline-flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={involvesInfosec}
                  onChange={(e) => setInvolvesInfosec(e.target.checked)}
                  className="rounded accent-[#C50337]"
                />
                <span>Доступ к ИС (ИБ)</span>
              </label>
              <label className="inline-flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={involvesIt}
                  onChange={(e) => setInvolvesIt(e.target.checked)}
                  className="rounded accent-[#C50337]"
                />
                <span>ИТ-проект (ДИТ)</span>
              </label>
              <label className="inline-flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={involvesRegional}
                  onChange={(e) => setInvolvesRegional(e.target.checked)}
                  className="rounded accent-[#C50337]"
                />
                <span>Участие РО</span>
              </label>
            </div>

            <div className="lg:col-span-2">
              <button
                onClick={() => void handleCalculateMatrix()}
                className="w-full py-2.5 px-4 rounded-xl bg-[#C50337] hover:opacity-90 text-sm font-semibold text-white transition"
              >
                Рассчитать
              </button>
            </div>
          </div>

          {calcResult && (
            <div className="p-5 rounded-xl bg-[#111115] border border-white/[0.14] space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span className="font-semibold text-white">
                  Правило № {calcResult.rule_number} — {calcResult.doc_type_name}
                </span>
                <span className="text-zinc-300">
                  Подписант: <strong className="text-white">{calcResult.signatory}</strong>
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
                {calcResult.stages.map((st) => (
                  <div
                    key={st.order}
                    className="p-3.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-xs space-y-1"
                  >
                    <div className="font-mono text-zinc-400">Этап {st.order}</div>
                    <div className="font-semibold text-white text-sm">{st.department}</div>
                    <div className="text-zinc-400">{st.role_name}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* All 13 Rules Table */}
        <div className="zyricon-glass-card rounded-2xl p-6 space-y-4">
          <h3 className="text-base font-semibold text-white">
            Таблица правил визирования ({rules.length})
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-white/[0.08] text-zinc-400 text-xs">
                  <th className="py-2.5 pr-2">№</th>
                  <th className="py-2.5 px-2">Вид документа</th>
                  <th className="py-2.5 px-2">Юр. служба</th>
                  <th className="py-2.5 px-2">ДОУ</th>
                  <th className="py-2.5 px-2">Кадры</th>
                  <th className="py-2.5 px-2">Условия (ИБ / ИТ / РО)</th>
                  <th className="py-2.5 pl-2">Подписант</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.06]">
                {rules.map((r) => {
                  const isSelected = r.doc_type_name === calcDocType;
                  return (
                    <tr
                      key={r.rule_number}
                      onClick={() => {
                        setCalcDocType(r.doc_type_name);
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                      className={`transition cursor-pointer ${
                        isSelected
                          ? "bg-[#C50337]/15 border-l-2 border-[#C50337]"
                          : "hover:bg-white/[0.04]"
                      }`}
                      title="Нажмите, чтобы рассчитать маршрут для этого правила"
                    >
                      <td className="py-3 pr-2 font-mono text-zinc-300">#{r.rule_number}</td>
                      <td className="py-3 px-2">
                        <div className="font-medium text-white">{r.doc_type_name}</div>
                        {r.condition_description && (
                          <div className="text-xs text-zinc-400 mt-0.5">{r.condition_description}</div>
                        )}
                      </td>
                      <td className="py-3 px-2">{r.requires_legal ? "Да" : "Модуль"}</td>
                      <td className="py-3 px-2">{r.requires_dou ? "Да" : "—"}</td>
                      <td className="py-3 px-2">{r.requires_hr ? "Да" : "—"}</td>
                      <td className="py-3 px-2 font-mono text-xs text-zinc-300">
                        ИБ:{r.requires_infosec} | ИТ:{r.requires_it} | РО:{r.requires_regional}
                      </td>
                      <td className="py-3 pl-2 text-white font-medium">{r.signatory}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

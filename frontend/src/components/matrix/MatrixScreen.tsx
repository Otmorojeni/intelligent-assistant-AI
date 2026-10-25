import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronDown,
  FileCheck2,
  GitMerge,
  Search,
  Shield,
  Sparkles,
  X,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import {
  calculateApprovalRoute,
  fetchApprovalRules,
} from "../../services/apiClient";
import {
  ApprovalCalculateResponse,
  ApprovalRuleItem,
} from "../../types/api";

const CANONICAL_RULES: ApprovalRuleItem[] = [
  {
    rule_number: 1,
    category: "internal",
    doc_type_name:
      "Приказы о работе в выходные и нерабочие праздничные дни, а также по иным вопросам рабочего календаря, подготовленные с использованием модульных документов",
    is_modular: true,
    requires_legal: true,
    requires_dou: true,
    requires_hr: true,
    requires_infosec: "no",
    requires_it: "no",
    requires_regional: "no",
    condition_description:
      "Обязательное визирование: Юридическое подразделение, Департамент ДОУ, Кадровое подразделение.",
    signatory: "Руководство Организации / Заместитель Председателя",
  },
  {
    rule_number: 2,
    category: "internal",
    doc_type_name:
      "Приказы о приеме и передаче дел и имущества при назначении, освобождении от должности, реорганизации и иных кадровых изменениях (без изменения доступа к ИС), подготовленные с использованием модульных документов",
    is_modular: true,
    requires_legal: true,
    requires_dou: true,
    requires_hr: true,
    requires_infosec: "no",
    requires_it: "no",
    requires_regional: "no",
    condition_description:
      "Стандартный маршрут: Юридическое подразделение, Департамент ДОУ, Кадровое подразделение (без затрагивания прав доступа к ИС).",
    signatory: "Руководство Организации / Руководитель подразделения",
  },
  {
    rule_number: 3,
    category: "internal",
    doc_type_name:
      "Приказы о приеме и передаче дел и имущества при назначении, освобождении от должности, реорганизации и иных кадровых изменениях (с изменением доступа к ИС), подготовленные с использованием модульных документов",
    is_modular: true,
    requires_legal: true,
    requires_dou: true,
    requires_hr: true,
    requires_infosec: "yes",
    requires_it: "no",
    requires_regional: "no",
    condition_description:
      "Департамент информационной безопасности визирует проект, если прием и передача дел связаны с предоставлением, изменением или прекращением доступа к информационным системам.",
    signatory: "Руководство Организации / Руководитель подразделения",
  },
  {
    rule_number: 4,
    category: "internal",
    doc_type_name:
      "Приказы по вопросам информационных систем, включая ввод в эксплуатацию, вывод из эксплуатации, опытную эксплуатацию, изменение компонентов и иные связанные вопросы, подготовленные с использованием модульных документов",
    is_modular: true,
    requires_legal: true,
    requires_dou: true,
    requires_hr: false,
    requires_infosec: "yes",
    requires_it: "yes",
    requires_regional: "no",
    condition_description:
      "Обязательное визирование: Юридическое подразделение, Департамент ДОУ, Департамент информационной безопасности, Департамент информационных технологий.",
    signatory: "Руководство Организации / Заместитель Председателя",
  },
  {
    rule_number: 5,
    category: "internal",
    doc_type_name:
      "Прочие приказы, в т.ч., подготовленные без использования модульных документов или с использованием модульных документов кроме указанных в пп.1-3 (включая назначение ответственных за ДОУ и утверждение ЛНА)",
    is_modular: false,
    requires_legal: true,
    requires_dou: true,
    requires_hr: false,
    requires_infosec: "no",
    requires_it: "no",
    requires_regional: "no",
    condition_description:
      "Обязательное визирование: Юридическое подразделение, Департамент ДОУ. Подразделение, компетенция которого затрагивается, включается в маршрут.",
    signatory: "Руководство Организации",
  },
  {
    rule_number: 6,
    category: "internal",
    doc_type_name:
      "Распоряжения о предоставлении материальной помощи и осуществлении иных выплат работникам",
    is_modular: false,
    requires_legal: false,
    requires_dou: true,
    requires_hr: true,
    requires_infosec: "no",
    requires_it: "no",
    requires_regional: "no",
    condition_description:
      "Визируется Департаментом ДОУ и Кадровым подразделением. Юридическое подразделение не требуется.",
    signatory: "Руководство Организации / Заместитель Председателя",
  },
  {
    rule_number: 7,
    category: "internal",
    doc_type_name:
      "Распоряжения о создании рабочих групп, проектных комитетов, комиссий и иных временных объединений (общего профиля)",
    is_modular: true,
    requires_legal: false,
    requires_dou: true,
    requires_hr: true,
    requires_infosec: "no",
    requires_it: "no",
    requires_regional: "no",
    condition_description:
      "Визируется Департаментом ДОУ и Кадровым подразделением (если объединение не связано с ИТ-проектами).",
    signatory: "Руководство Организации / Курирующий Заместитель Председателя",
  },
  {
    rule_number: 8,
    category: "internal",
    doc_type_name:
      "Распоряжения о создании рабочих групп, проектных комитетов, комиссий и иных временных объединений для реализации ИТ-проектов или вопросов ИС",
    is_modular: true,
    requires_legal: false,
    requires_dou: true,
    requires_hr: true,
    requires_infosec: "no",
    requires_it: "yes",
    requires_regional: "no",
    condition_description:
      "Департамент информационных технологий визирует проект, если временное объединение создается для реализации ИТ-проекта или вопросов ИС.",
    signatory: "Руководство Организации / Курирующий Заместитель Председателя",
  },
  {
    rule_number: 9,
    category: "internal",
    doc_type_name:
      "Прочие распоряжения, подготовленные без использования модульных документов или с использованием модульных документов кроме указанных в пп.5-6 (включая проведение внутреннего аудита процессов)",
    is_modular: false,
    requires_legal: true,
    requires_dou: true,
    requires_hr: false,
    requires_infosec: "no",
    requires_it: "no",
    requires_regional: "no",
    condition_description:
      "Обязательное визирование: Юридическое подразделение, Департамент ДОУ.",
    signatory: "Руководство Организации / Руководитель подразделения",
  },
  {
    rule_number: 10,
    category: "external",
    doc_type_name:
      "Письма за подписью Руководства Организации, адресуемые органам государственной власти, Администрации Президента РФ, членам Совета Федерации, депутатам Государственной Думы, Аппарату Правительства РФ, Счетной палате РФ",
    is_modular: false,
    requires_legal: true,
    requires_dou: true,
    requires_hr: false,
    requires_infosec: "no",
    requires_it: "no",
    requires_regional: "no",
    condition_description:
      "Обязательное визирование: Юридическое подразделение, Департамент ДОУ, Департамент внутреннего контроля.",
    signatory: "Председатель Организации / Заместитель Председателя",
  },
  {
    rule_number: 11,
    category: "external",
    doc_type_name:
      "Письма за подписью Руководства Организации, адресуемые руководству иностранных организаций, центральных (национальных) банков иностранных государств, а также международных банков и иных международных организаций",
    is_modular: false,
    requires_legal: true,
    requires_dou: true,
    requires_hr: false,
    requires_infosec: "no",
    requires_it: "no",
    requires_regional: "no",
    condition_description:
      "Обязательное визирование: Юридическое подразделение, Департамент ДОУ, Департамент международного сотрудничества.",
    signatory: "Председатель Организации / Заместитель Председателя",
  },
  {
    rule_number: 12,
    category: "external",
    doc_type_name:
      "Письма российским юридическим лицам за подписью Руководства Организации или руководителей СП ЦА",
    is_modular: false,
    requires_legal: true,
    requires_dou: true,
    requires_hr: false,
    requires_infosec: "no",
    requires_it: "no",
    requires_regional: "no",
    condition_description:
      "Обязательное визирование: Юридическое подразделение, Департамент ДОУ.",
    signatory: "Руководство Организации / Руководитель СП",
  },
  {
    rule_number: 13,
    category: "external",
    doc_type_name:
      "Письма российским юридическим лицам за подписью руководства РО Организации (с участием региональных отделений)",
    is_modular: false,
    requires_legal: true,
    requires_dou: true,
    requires_hr: false,
    requires_infosec: "no",
    requires_it: "no",
    requires_regional: "yes",
    condition_description:
      "Визируется Юридическим подразделением, Департаментом ДОУ и службой документационного обеспечения РО Организации.",
    signatory: "Руководитель РО Организации",
  },
];

type CategoryFilter = "all" | "orders" | "directives" | "letters";

function getRuleCategoryLabel(ruleNumber: number): string {
  if (ruleNumber <= 5) return "Приказ";
  if (ruleNumber <= 9) return "Распоряжение";
  return "Исходящее письмо";
}

export const MatrixScreen: React.FC = () => {
  const { token } = useAuth();
  const [rules, setRules] = useState<ApprovalRuleItem[]>(CANONICAL_RULES);
  const [calcDocType, setCalcDocType] = useState<string>(CANONICAL_RULES[0].doc_type_name);
  const [isRuleDropdownOpen, setIsRuleDropdownOpen] = useState(false);
  const [ruleSearchQuery, setRuleSearchQuery] = useState("");
  const [activeCategoryFilter, setActiveCategoryFilter] = useState<CategoryFilter>("all");
  const [isCalculating, setIsCalculating] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const ruleDropdownRef = useRef<HTMLDivElement>(null);

  const [usesModule, setUsesModule] = useState(true);
  const [involvesInfosec, setInvolvesInfosec] = useState(false);
  const [involvesIt, setInvolvesIt] = useState(false);
  const [involvesRegional, setInvolvesRegional] = useState(false);
  const [calcResult, setCalcResult] = useState<ApprovalCalculateResponse | null>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        ruleDropdownRef.current &&
        !ruleDropdownRef.current.contains(event.target as Node)
      ) {
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
      if (list && list.length > 0) {
        setRules(list);
      }
    } catch {
      // Keep canonical fallback
    }
  }, [token]);

  useEffect(() => {
    void loadRules();
  }, [loadRules]);

  const handleSelectRule = (rule: ApprovalRuleItem) => {
    setCalcDocType(rule.doc_type_name);
    setIsRuleDropdownOpen(false);
    setRuleSearchQuery("");
    // Synchronize checkboxes with rule parameters
    setUsesModule(rule.is_modular);
    setInvolvesInfosec(rule.requires_infosec === "yes");
    setInvolvesIt(rule.requires_it === "yes");
    setInvolvesRegional(rule.requires_regional === "yes");
  };

  const handleCalculateMatrix = async () => {
    setIsCalculating(true);
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
      // Fallback local calculate for offline mode
      const selected = rules.find((r) => r.doc_type_name === calcDocType) || rules[0];
      const stages = [
        ...(selected.requires_legal ? [{ order: 1, department: "Юридическое подразделение", role_name: "Юрисконсульт", reason: "Правовая экспертиза" }] : []),
        ...(selected.requires_dou ? [{ order: 2, department: "Департамент ДОУ", role_name: "Специалист ДОУ", reason: "Нормоконтроль и делопроизводство" }] : []),
        ...(selected.requires_hr ? [{ order: 3, department: "Кадровое подразделение", role_name: "Инспектор по кадрам", reason: "Кадровые изменения" }] : []),
        ...(involvesInfosec || selected.requires_infosec === "yes" ? [{ order: 4, department: "Департамент информационной безопасности", role_name: "Офицер ИБ", reason: "Контроль прав доступа к ИС" }] : []),
        ...(involvesIt || selected.requires_it === "yes" ? [{ order: 5, department: "Департамент информационных технологий", role_name: "Архитектор ИТ", reason: "ИТ-инфраструктура" }] : []),
        ...(involvesRegional || selected.requires_regional === "yes" ? [{ order: 6, department: "Подразделение ДОУ РО Организации", role_name: "Специалист РО", reason: "Участие РО" }] : []),
      ].map((st, idx) => ({ ...st, order: idx + 1 }));

      setCalcResult({
        rule_number: selected.rule_number,
        doc_type_name: selected.doc_type_name,
        is_modular: selected.is_modular,
        signatory: selected.signatory,
        stages: stages.length > 0 ? stages : [{ order: 1, department: "Департамент ДОУ", role_name: "Специалист ДОУ", reason: "Нормоконтроль" }],
        notes: [selected.condition_description || "Стандартный маршрут"],
      });
    } finally {
      setIsCalculating(false);
    }
  };

  const currentRule = useMemo(() => {
    return rules.find((r) => r.doc_type_name === calcDocType) || rules[0];
  }, [rules, calcDocType]);

  const filteredRules = useMemo(() => {
    return rules.filter((r) => {
      // Category filter
      if (activeCategoryFilter === "orders" && r.rule_number > 5) return false;
      if (activeCategoryFilter === "directives" && (r.rule_number < 6 || r.rule_number > 9)) return false;
      if (activeCategoryFilter === "letters" && r.rule_number < 10) return false;

      // Text search query
      if (!ruleSearchQuery.trim()) return true;
      const q = ruleSearchQuery.toLowerCase().trim();
      return (
        r.rule_number.toString().includes(q) ||
        r.doc_type_name.toLowerCase().includes(q) ||
        (r.condition_description && r.condition_description.toLowerCase().includes(q)) ||
        (r.signatory && r.signatory.toLowerCase().includes(q))
      );
    });
  }, [rules, ruleSearchQuery, activeCategoryFilter]);

  return (
    <div
      ref={containerRef}
      className="flex-1 h-screen zyricon-stage-bg overflow-y-auto px-4 sm:px-8 lg:px-12 py-8"
    >
      <div className="max-w-5xl mx-auto space-y-6">
        {/* Title Banner */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2.5">
              <span>Маршруты согласования документов</span>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-[#C50337]/20 border border-[#C50337]/40 text-rose-300 font-medium">
                ОД-184
              </span>
            </h1>
            <p className="text-sm text-zinc-400 mt-1">
              Подбор обязательных согласующих подразделений и интерактивная матрица из 13 правил визирования
            </p>
          </div>
        </div>

        {/* Route Calculator Card */}
        <div
          className={`zyricon-glass-card rounded-3xl p-6 sm:p-7 space-y-6 border border-white/[0.14] shadow-2xl backdrop-blur-2xl relative ${
            isRuleDropdownOpen ? "z-30" : "z-10"
          }`}
        >
          <div className="flex items-center justify-between border-b border-white/[0.08] pb-4">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-xl bg-[#C50337]/15 border border-[#C50337]/30 text-[#C50337]">
                <GitMerge className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-semibold text-white">
                  Калькулятор маршрута визирования
                </h2>
                <p className="text-xs text-zinc-400">
                  Выберите вид документа и уточните параметры согласования
                </p>
              </div>
            </div>
            {currentRule && (
              <div className="hidden sm:inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/[0.04] border border-white/[0.08] text-xs text-zinc-300 font-mono">
                <span className="w-2 h-2 rounded-full bg-[#C50337]" />
                <span>Правило #{currentRule.rule_number}</span>
                <span className="text-zinc-500">•</span>
                <span className="text-zinc-400">{getRuleCategoryLabel(currentRule.rule_number)}</span>
              </div>
            )}
          </div>

          {/* Document Rule Selection — Constrained & Responsive */}
          <div className="space-y-2 relative z-30" ref={ruleDropdownRef}>
            <div className="flex items-center justify-between text-xs font-semibold text-zinc-300 uppercase tracking-wider">
              <span>1. Вид документа (Правила согласования № 1–13)</span>
              <span className="text-[11px] text-zinc-400 font-normal lowercase tracking-normal">
                нажмите для выбора правила
              </span>
            </div>

            {/* Custom Dropdown Trigger Button */}
            <button
              type="button"
              onClick={() => setIsRuleDropdownOpen((prev) => !prev)}
              className={`w-full text-left p-3.5 sm:p-4 rounded-2xl bg-[#0D0D11] border transition-all duration-150 flex items-center justify-between gap-3 select-none ${
                isRuleDropdownOpen
                  ? "border-[#C50337] ring-1 ring-[#C50337] shadow-[0_0_20px_rgba(197,3,55,0.25)]"
                  : "border-white/[0.14] hover:border-white/30 hover:bg-white/[0.02]"
              }`}
              aria-expanded={isRuleDropdownOpen}
              aria-haspopup="listbox"
            >
              <div className="flex items-start sm:items-center gap-3 min-w-0 flex-1">
                <span className="shrink-0 mt-0.5 sm:mt-0 px-2.5 py-1 rounded-lg bg-[#C50337]/20 border border-[#C50337]/40 text-xs font-bold text-rose-300">
                  № {currentRule?.rule_number || 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-white leading-snug line-clamp-2">
                    {currentRule?.doc_type_name || calcDocType}
                  </div>
                  {currentRule?.condition_description && (
                    <div className="text-xs text-zinc-400 mt-0.5 line-clamp-1">
                      {currentRule.condition_description}
                    </div>
                  )}
                </div>
              </div>
              <ChevronDown
                className={`w-5 h-5 text-zinc-400 shrink-0 transition-transform duration-200 ${
                  isRuleDropdownOpen ? "rotate-180 text-white" : ""
                }`}
              />
            </button>

            {/* Custom Dropdown Popover — Strictly Constrained, Never Overflows */}
            {isRuleDropdownOpen && (
              <div className="absolute left-0 right-0 top-full mt-2 z-50 rounded-2xl bg-[#111116] border border-white/[0.18] shadow-[0_20px_50px_rgba(0,0,0,0.85)] backdrop-blur-2xl overflow-hidden flex flex-col max-h-[460px] w-full max-w-full animate-in fade-in zoom-in-95 duration-150">
                {/* Search Header inside Dropdown */}
                <div className="p-3 border-b border-white/[0.08] bg-[#15151B] sticky top-0 z-10 space-y-2.5 shrink-0">
                  <div className="relative">
                    <Search className="w-4 h-4 text-zinc-400 absolute left-3 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      value={ruleSearchQuery}
                      onChange={(e) => setRuleSearchQuery(e.target.value)}
                      placeholder="Поиск правила по номеру, названию или согласующим..."
                      className="w-full pl-9 pr-8 py-2 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-xs sm:text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-[#C50337] focus:ring-1 focus:ring-[#C50337] transition"
                      autoFocus
                    />
                    {ruleSearchQuery && (
                      <button
                        type="button"
                        onClick={() => setRuleSearchQuery("")}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-white transition"
                        title="Очистить поиск"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    )}
                  </div>

                  {/* Fast Category Filter Chips */}
                  <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5 text-xs">
                    {(
                      [
                        { id: "all", label: "Все (13)" },
                        { id: "orders", label: "Приказы (1–5)" },
                        { id: "directives", label: "Распоряжения (6–9)" },
                        { id: "letters", label: "Письма (10–13)" },
                      ] as const
                    ).map((f) => (
                      <button
                        key={f.id}
                        type="button"
                        onClick={() => setActiveCategoryFilter(f.id)}
                        className={`px-2.5 py-1 rounded-lg font-medium whitespace-nowrap transition ${
                          activeCategoryFilter === f.id
                            ? "bg-[#C50337] text-white shadow-sm"
                            : "bg-white/[0.04] text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.08]"
                        }`}
                      >
                        {f.label}
                      </button>
                    ))}
                    <span className="ml-auto text-[11px] text-zinc-400 shrink-0 pr-1">
                      {filteredRules.length} из {rules.length}
                    </span>
                  </div>
                </div>

                {/* Scrollable Rules List with Word-Wrap & No Horizontal Spill */}
                <div className="overflow-y-auto flex-1 min-h-0 divide-y divide-white/[0.05] p-1.5 space-y-0.5">
                  {filteredRules.length === 0 ? (
                    <div className="p-6 text-center text-xs text-zinc-400 space-y-1">
                      <p className="font-semibold text-zinc-300">Правила не найдены</p>
                      <p>Попробуйте изменить поисковый запрос или фильтр</p>
                    </div>
                  ) : (
                    filteredRules.map((r) => {
                      const isSelected = r.doc_type_name === calcDocType;
                      return (
                        <button
                          key={r.rule_number}
                          type="button"
                          onClick={() => handleSelectRule(r)}
                          className={`w-full text-left p-3 rounded-xl transition flex items-start gap-3 ${
                            isSelected
                              ? "bg-[#C50337]/15 border border-[#C50337]/40 text-white shadow-sm"
                              : "hover:bg-white/[0.05] text-zinc-200 border border-transparent"
                          }`}
                        >
                          <span
                            className={`shrink-0 mt-0.5 px-2 py-0.5 rounded-md text-xs font-bold ${
                              isSelected
                                ? "bg-[#C50337] text-white"
                                : "bg-white/[0.08] text-rose-300 border border-white/[0.08]"
                            }`}
                          >
                            № {r.rule_number}
                          </span>

                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-[11px] text-zinc-400 uppercase font-semibold tracking-wider">
                                {getRuleCategoryLabel(r.rule_number)}
                              </span>
                              {r.is_modular && (
                                <span className="text-[10px] px-1.5 py-0.2 rounded bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                                  Модульный
                                </span>
                              )}
                            </div>
                            <div className="text-xs sm:text-sm font-semibold leading-snug break-words text-white mt-0.5">
                              {r.doc_type_name}
                            </div>
                            {r.condition_description && (
                              <div className="text-xs text-zinc-400 mt-1 break-words leading-relaxed">
                                {r.condition_description}
                              </div>
                            )}
                          </div>

                          {isSelected && (
                            <Check className="w-4 h-4 text-[#C50337] shrink-0 mt-1" />
                          )}
                        </button>
                      );
                    })
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Route Options & Condition Flags */}
          <div className="space-y-2 pt-1">
            <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider">
              2. Дополнительные условия маршрутизации
            </label>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
              <label
                className={`flex items-center gap-2.5 p-3 rounded-2xl border cursor-pointer transition select-none ${
                  usesModule
                    ? "bg-white/[0.08] border-white/30 text-white"
                    : "bg-[#0D0D11] border-white/[0.08] text-zinc-400 hover:border-white/20 hover:text-zinc-300"
                }`}
              >
                <input
                  type="checkbox"
                  checked={usesModule}
                  onChange={(e) => setUsesModule(e.target.checked)}
                  className="w-4 h-4 rounded accent-[#C50337]"
                />
                <span className="text-xs sm:text-sm font-medium">Модульный шаблон</span>
              </label>

              <label
                className={`flex items-center gap-2.5 p-3 rounded-2xl border cursor-pointer transition select-none ${
                  involvesInfosec
                    ? "bg-[#C50337]/15 border-[#C50337]/50 text-white"
                    : "bg-[#0D0D11] border-white/[0.08] text-zinc-400 hover:border-white/20 hover:text-zinc-300"
                }`}
              >
                <input
                  type="checkbox"
                  checked={involvesInfosec}
                  onChange={(e) => setInvolvesInfosec(e.target.checked)}
                  className="w-4 h-4 rounded accent-[#C50337]"
                />
                <span className="text-xs sm:text-sm font-medium">Доступ к ИС (ИБ)</span>
              </label>

              <label
                className={`flex items-center gap-2.5 p-3 rounded-2xl border cursor-pointer transition select-none ${
                  involvesIt
                    ? "bg-white/[0.08] border-white/30 text-white"
                    : "bg-[#0D0D11] border-white/[0.08] text-zinc-400 hover:border-white/20 hover:text-zinc-300"
                }`}
              >
                <input
                  type="checkbox"
                  checked={involvesIt}
                  onChange={(e) => setInvolvesIt(e.target.checked)}
                  className="w-4 h-4 rounded accent-[#C50337]"
                />
                <span className="text-xs sm:text-sm font-medium">ИТ-проект (ДИТ)</span>
              </label>

              <label
                className={`flex items-center gap-2.5 p-3 rounded-2xl border cursor-pointer transition select-none ${
                  involvesRegional
                    ? "bg-white/[0.08] border-white/30 text-white"
                    : "bg-[#0D0D11] border-white/[0.08] text-zinc-400 hover:border-white/20 hover:text-zinc-300"
                }`}
              >
                <input
                  type="checkbox"
                  checked={involvesRegional}
                  onChange={(e) => setInvolvesRegional(e.target.checked)}
                  className="w-4 h-4 rounded accent-[#C50337]"
                />
                <span className="text-xs sm:text-sm font-medium">Участие РО</span>
              </label>
            </div>
          </div>

          {/* Action Row */}
          <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-white/[0.08]">
            <div className="text-xs text-zinc-400 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-[#C50337]" />
              <span>
                Инициатор маршрута: <strong className="text-white">Департамент ДОУ</strong>
              </span>
            </div>

            <button
              type="button"
              disabled={isCalculating}
              onClick={() => void handleCalculateMatrix()}
              className="w-full sm:w-auto py-3 px-6 rounded-xl bg-[#C50337] hover:bg-[#a6022e] active:scale-[0.99] text-sm font-semibold text-white shadow-[0_0_20px_rgba(197,3,55,0.35)] transition flex items-center justify-center gap-2 disabled:opacity-50"
            >
              {isCalculating ? (
                <>
                  <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  <span>Расчет маршрута...</span>
                </>
              ) : (
                <>
                  <GitMerge className="w-4 h-4" />
                  <span>Рассчитать маршрут согласования</span>
                </>
              )}
            </button>
          </div>

          {/* Calculation Result Pipeline */}
          {calcResult && (
            <div className="p-5 sm:p-6 rounded-2xl bg-[#0D0D11] border border-white/[0.14] space-y-4 animate-in fade-in duration-200">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-white/[0.08] pb-3 text-sm">
                <div>
                  <span className="font-semibold text-white">
                    Правило № {calcResult.rule_number} — {calcResult.doc_type_name}
                  </span>
                </div>
                <div className="text-zinc-300 shrink-0">
                  Подписант: <strong className="text-white">{calcResult.signatory}</strong>
                </div>
              </div>

              {/* Stage Flow */}
              <div className="space-y-2">
                <div className="text-xs font-semibold text-zinc-400 uppercase tracking-wider">
                  Последовательность этапов согласования:
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                  {calcResult.stages.map((st, idx) => (
                    <div
                      key={st.order}
                      className="p-3.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-xs space-y-1.5 relative hover:border-white/20 transition"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs font-bold text-rose-300">
                          Этап #{st.order}
                        </span>
                        {idx < calcResult.stages.length - 1 && (
                          <ArrowRight className="hidden lg:block w-3.5 h-3.5 text-zinc-500 absolute -right-2 top-1/2 -translate-y-1/2 z-10" />
                        )}
                      </div>
                      <div className="font-semibold text-white text-sm leading-snug">
                        {st.department}
                      </div>
                      <div className="text-zinc-400 text-xs">{st.role_name}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* All 13 Rules Table */}
        <div className="zyricon-glass-card rounded-3xl p-6 sm:p-7 space-y-4 border border-white/[0.14] shadow-2xl backdrop-blur-2xl relative z-0">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-base font-semibold text-white">
                Таблица правил визирования ({rules.length})
              </h3>
              <p className="text-xs text-zinc-400 mt-0.5">
                Кликните по любой строке для мгновенного переноса правила в калькулятор
              </p>
            </div>
            <div className="text-xs text-zinc-400">
              Показано: {rules.length} правил ОД-184
            </div>
          </div>

          <div className="overflow-x-auto rounded-2xl border border-white/[0.08]">
            <table className="w-full text-left border-collapse text-sm">
              <thead>
                <tr className="border-b border-white/[0.08] bg-white/[0.02] text-zinc-400 text-xs font-semibold">
                  <th className="py-3 px-3">№</th>
                  <th className="py-3 px-3">Вид документа</th>
                  <th className="py-3 px-2">Юр. служба</th>
                  <th className="py-3 px-2">ДОУ</th>
                  <th className="py-3 px-2">Кадры</th>
                  <th className="py-3 px-3">Условия (ИБ / ИТ / РО)</th>
                  <th className="py-3 px-3">Подписант</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05]">
                {rules.map((r) => {
                  const isSelected = r.doc_type_name === calcDocType;
                  return (
                    <tr
                      key={r.rule_number}
                      onClick={() => {
                        handleSelectRule(r);
                        containerRef.current?.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                      className={`transition cursor-pointer ${
                        isSelected
                          ? "bg-[#C50337]/15 border-l-4 border-[#C50337]"
                          : "hover:bg-white/[0.04]"
                      }`}
                      title="Кликните, чтобы выбрать это правило в калькуляторе"
                    >
                      <td className="py-3.5 px-3 font-mono font-bold text-zinc-300">
                        #{r.rule_number}
                      </td>
                      <td className="py-3.5 px-3 max-w-md">
                        <div className="font-semibold text-white leading-snug">
                          {r.doc_type_name}
                        </div>
                        {r.condition_description && (
                          <div className="text-xs text-zinc-400 mt-1 leading-relaxed">
                            {r.condition_description}
                          </div>
                        )}
                      </td>
                      <td className="py-3.5 px-2">
                        <span
                          className={`text-xs px-2 py-0.5 rounded ${
                            r.requires_legal
                              ? "bg-emerald-500/15 text-emerald-300"
                              : "bg-white/[0.05] text-zinc-400"
                          }`}
                        >
                          {r.requires_legal ? "Да" : "Модуль"}
                        </span>
                      </td>
                      <td className="py-3.5 px-2">
                        <span
                          className={`text-xs px-2 py-0.5 rounded ${
                            r.requires_dou
                              ? "bg-emerald-500/15 text-emerald-300"
                              : "bg-white/[0.05] text-zinc-400"
                          }`}
                        >
                          {r.requires_dou ? "Да" : "—"}
                        </span>
                      </td>
                      <td className="py-3.5 px-2">
                        <span
                          className={`text-xs px-2 py-0.5 rounded ${
                            r.requires_hr
                              ? "bg-emerald-500/15 text-emerald-300"
                              : "bg-white/[0.05] text-zinc-400"
                          }`}
                        >
                          {r.requires_hr ? "Да" : "—"}
                        </span>
                      </td>
                      <td className="py-3.5 px-3 font-mono text-xs text-zinc-300">
                        <div className="space-y-0.5">
                          <div>ИБ: <span className={r.requires_infosec === "yes" ? "text-rose-300 font-bold" : "text-zinc-500"}>{r.requires_infosec}</span></div>
                          <div>ИТ: <span className={r.requires_it === "yes" ? "text-cyan-300 font-bold" : "text-zinc-500"}>{r.requires_it}</span></div>
                          <div>РО: <span className={r.requires_regional === "yes" ? "text-amber-300 font-bold" : "text-zinc-500"}>{r.requires_regional}</span></div>
                        </div>
                      </td>
                      <td className="py-3.5 px-3 text-white font-medium text-xs leading-relaxed">
                        {r.signatory}
                      </td>
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

import React, { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  Copy,
  Download,
  FileSpreadsheet,
  FolderKanban,
  GitMerge,
  Lock,
  Wand2,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import {
  downloadGeneratedDocx,
  fetchProjectCards,
  fetchTemplates,
  generateModularDocument,
} from "../../services/apiClient";
import {
  DocumentGenerateResponse,
  ProjectCardItem,
  TemplateModuleInfo,
} from "../../types/api";

interface ConstructorScreenProps {
  initialModuleCode?: string | null;
}

export const ConstructorScreen: React.FC<ConstructorScreenProps> = ({
  initialModuleCode,
}) => {
  const { role, token } = useAuth();
  const [templates, setTemplates] = useState<TemplateModuleInfo[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateModuleInfo | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [executorName, setExecutorName] = useState("Иванов И.И.");
  const [executorDept, setExecutorDept] = useState("Департамент ДОУ");
  const [signatoryName, setSignatoryName] = useState("Петров П.П.");
  const [accessLevel, setAccessLevel] = useState("public");
  const [projectTitle, setProjectTitle] = useState("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [genResult, setGenResult] = useState<DocumentGenerateResponse | null>(null);
  const [projects, setProjects] = useState<ProjectCardItem[]>([]);
  const [copiedNote, setCopiedNote] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const loadProjects = useCallback(async () => {
    try {
      const list = await fetchProjectCards(token);
      setProjects(list);
    } catch {
      // ignore
    }
  }, [token]);

  const applyTemplateDefaults = useCallback((tpl: TemplateModuleInfo) => {
    setSelectedTemplate(tpl);
    setGenResult(null);
    setErrorMsg(null);
    setProjectTitle(tpl.title);
    const defaults: Record<string, string> = {};
    for (const f of tpl.fields_schema || []) {
      defaults[f.name] = f.default || "";
    }
    setFormValues(defaults);
  }, []);

  useEffect(() => {
    async function init() {
      try {
        const list = await fetchTemplates(token);
        setTemplates(list);
        if (list.length > 0) {
          const target =
            (initialModuleCode && list.find((t) => t.module_code === initialModuleCode)) ||
            list[0];
          applyTemplateDefaults(target);
        }
      } catch (err: any) {
        setErrorMsg(err?.message || "Не удалось загрузить каталог шаблонов");
      }
    }
    void init();
  }, [initialModuleCode, token, applyTemplateDefaults]);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects, role]);

  const handleFillDemoValues = () => {
    if (!selectedTemplate) return;
    const next: Record<string, string> = {};
    for (const f of selectedTemplate.fields_schema || []) {
      next[f.name] = f.default || "По согласованию с подразделением";
    }
    setFormValues(next);
    setExecutorName("Соколов А.В.");
    setExecutorDept("Департамент информационных технологий");
    setSignatoryName("Заместитель Председателя Смирнов К.Н.");
  };

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTemplate || isGenerating) return;
    setIsGenerating(true);
    setErrorMsg(null);
    try {
      const res = await generateModularDocument(
        {
          module_code: selectedTemplate.module_code,
          executor_name: executorName,
          executor_department: executorDept,
          signatory_name: signatoryName,
          access_level: accessLevel,
          fields: formValues,
          user_role: role,
          project_title: projectTitle || selectedTemplate.title,
        },
        token
      );
      setGenResult(res);
      await loadProjects();
    } catch (err: any) {
      setErrorMsg(err?.message || "Ошибка генерации документа");
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="flex-1 h-[calc(100vh-4rem)] zyricon-stage-bg overflow-y-auto px-6 sm:px-12 py-8 space-y-6">
      {/* Top Header */}
      <div className="max-w-6xl mx-auto flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="text-xs font-mono uppercase tracking-widest text-zinc-400">
            Автоматическая очистка по Разделу 3.3 • Обязательная отметка п. 2.3
          </div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-white mt-1">
            Конструктор модульных документов (УТВ-01 .. УТВ-07)
          </h1>
        </div>

        <button
          type="button"
          onClick={handleFillDemoValues}
          className="px-4 py-2.5 rounded-xl bg-white/[0.08] hover:bg-white/[0.14] border border-white/[0.14] text-sm font-medium text-white flex items-center gap-2 transition"
        >
          <Wand2 className="w-4 h-4 text-[#C50337]" />
          <span>Заполнить демо-реквизитами</span>
        </button>
      </div>

      {/* Main Grid */}
      <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left column: 7 Templates Catalog */}
        <div className="lg:col-span-4 space-y-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-zinc-400 px-1">
            Утвержденные шаблоны ({templates.length})
          </div>
          <div className="space-y-2.5">
            {templates.map((tpl) => {
              const active = selectedTemplate?.module_code === tpl.module_code;
              return (
                <button
                  key={tpl.module_code}
                  onClick={() => applyTemplateDefaults(tpl)}
                  className={`w-full text-left p-4 rounded-2xl transition border ${
                    active
                      ? "bg-[#14141A] border-[#C50337] shadow-lg"
                      : "zyricon-glass-card hover:border-white/[0.2]"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <span className="text-xs font-mono font-semibold px-2.5 py-0.5 rounded bg-white/[0.08] text-white">
                      {tpl.reg_number} • {tpl.module_code}
                    </span>
                    <span className="text-xs px-2 py-0.5 rounded bg-white/[0.05] text-zinc-300">
                      {tpl.doc_kind === "order" ? "Приказ" : "Распоряжение"}
                    </span>
                  </div>
                  <div className="text-sm font-semibold text-white leading-snug">{tpl.title}</div>
                  <div className="text-xs text-zinc-400 mt-1.5">
                    Реквизитов: {tpl.fields_schema?.length || 0} • Редакция {tpl.version}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right column: Form + Generated Output */}
        <div className="lg:col-span-8 space-y-6">
          {selectedTemplate && (
            <form
              onSubmit={handleGenerate}
              className="zyricon-glass-card rounded-2xl p-6 space-y-5 border border-white/[0.12]"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.08] pb-4">
                <div>
                  <div className="text-xs font-mono text-zinc-400">
                    Шаблон {selectedTemplate.reg_number} ({selectedTemplate.module_code})
                  </div>
                  <h2 className="text-lg font-semibold text-white mt-0.5">
                    {selectedTemplate.title}
                  </h2>
                </div>
                <span className="text-xs px-3 py-1 rounded-full bg-white/[0.07] text-zinc-200 border border-white/[0.12]">
                  Защита служебных зон ЭП и Рег. номера
                </span>
              </div>

              {errorMsg && (
                <div className="p-4 rounded-xl bg-[#C50337]/20 border border-[#C50337]/50 text-sm text-white">
                  {errorMsg}
                </div>
              )}

              {/* Project Card Metadata Fields */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
                <div>
                  <label className="block text-xs font-medium text-zinc-300 mb-1.5">
                    ФИО исполнителя (карточка проекта п. 2.3)
                  </label>
                  <input
                    type="text"
                    required
                    value={executorName}
                    onChange={(e) => setExecutorName(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white focus:border-[#C50337] focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-zinc-300 mb-1.5">
                    Подразделение-инициатор
                  </label>
                  <input
                    type="text"
                    required
                    value={executorDept}
                    onChange={(e) => setExecutorDept(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white focus:border-[#C50337] focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-zinc-300 mb-1.5">
                    Утверждающее лицо (Подписант)
                  </label>
                  <input
                    type="text"
                    required
                    value={signatoryName}
                    onChange={(e) => setSignatoryName(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white focus:border-[#C50337] focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-zinc-300 mb-1.5">
                    Гриф доступа карточки проекта (RBAC)
                  </label>
                  <select
                    value={accessLevel}
                    onChange={(e) => setAccessLevel(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white focus:border-[#C50337] focus:outline-none"
                  >
                    <option value="public">Public (Общедоступный)</option>
                    <option value="internal">Internal (Внутренний)</option>
                    <option value="dsp">ДСП (Для служебного пользования)</option>
                    <option value="confidential">Confidential (Конфиденциально)</option>
                  </select>
                </div>
              </div>

              {/* Dynamic Variable Fields */}
              <div className="pt-4 border-t border-white/[0.08] space-y-4">
                <div className="text-sm font-semibold text-white">
                  Реквизиты текста документа ({selectedTemplate.fields_schema.length})
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {selectedTemplate.fields_schema.map((field) => (
                    <div key={field.name} className="sm:col-span-1">
                      <label className="block text-xs font-medium text-zinc-300 mb-1.5">
                        {field.label}{" "}
                        {field.required && <span className="text-[#C50337]">*</span>}
                      </label>
                      <input
                        type="text"
                        required={Boolean(field.required)}
                        value={formValues[field.name] ?? ""}
                        onChange={(e) =>
                          setFormValues((prev) => ({
                            ...prev,
                            [field.name]: e.target.value,
                          }))
                        }
                        placeholder={field.default || field.description || ""}
                        className="w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white focus:border-[#C50337] focus:outline-none"
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div className="pt-3 flex items-center justify-end">
                <button
                  type="submit"
                  disabled={isGenerating}
                  className="px-6 py-3 rounded-xl bg-[#C50337] hover:opacity-90 disabled:opacity-45 text-sm font-semibold text-white flex items-center gap-2.5 transition"
                >
                  <FileSpreadsheet className="w-4 h-4" />
                  <span>
                    {isGenerating
                      ? "Очистка по п. 3.3 и сборка .DOCX..."
                      : "Сформировать проект .DOCX"}
                  </span>
                </button>
              </div>
            </form>
          )}

          {/* Generated Document Result Panel */}
          {genResult && (
            <div className="p-6 rounded-2xl bg-[#111115] border border-white/[0.18] space-y-5 shadow-xl">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[#C50337]/20 border border-[#C50337]/40 flex items-center justify-center">
                    <CheckCircle2 className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <div className="text-base font-semibold text-white">
                      Проект документа сформирован по Разделу 3.3
                    </div>
                    <div className="text-xs font-mono text-zinc-400 mt-0.5">
                      {genResult.file_name}
                    </div>
                  </div>
                </div>

                <button
                  onClick={() => void downloadGeneratedDocx(genResult.file_name, token)}
                  className="px-5 py-2.5 rounded-xl bg-[#C50337] hover:opacity-90 text-sm font-semibold text-white flex items-center gap-2 transition"
                >
                  <Download className="w-4 h-4" />
                  <span>Скачать .DOCX</span>
                </button>
              </div>

              {/* Mandatory Note Section 2.3 */}
              <div className="p-4 rounded-xl bg-black/50 border border-white/[0.1] flex items-center justify-between gap-3">
                <div className="text-sm">
                  <div className="text-zinc-400 mb-1">
                    Обязательная отметка в карточке проекта ИИС ДО (п. 2.3):
                  </div>
                  <div className="font-mono text-white">{genResult.note_text}</div>
                </div>
                <button
                  onClick={() => {
                    navigator.clipboard?.writeText(genResult.note_text);
                    setCopiedNote(true);
                    setTimeout(() => setCopiedNote(false), 1800);
                  }}
                  className="px-3.5 py-2 rounded-lg bg-white/[0.08] hover:bg-white/[0.14] text-xs font-medium text-white shrink-0 flex items-center gap-1.5"
                >
                  <Copy className="w-3.5 h-3.5" />
                  <span>{copiedNote ? "Скопировано" : "Скопировать"}</span>
                </button>
              </div>

              {/* 5-stage approval route */}
              <div className="space-y-2.5">
                <div className="text-sm font-semibold text-white flex items-center gap-2">
                  <GitMerge className="w-4 h-4 text-[#C50337]" />
                  <span>Маршрут согласования ({genResult.approval_route.length} этапов):</span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-5 gap-2.5">
                  {genResult.approval_route.map((st) => (
                    <div
                      key={st.order}
                      className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.08] text-xs space-y-1"
                    >
                      <div className="font-mono text-zinc-400">Этап {st.order}</div>
                      <div className="font-semibold text-white text-sm leading-snug">
                        {st.department}
                      </div>
                      <div className="text-zinc-400">{st.role_name}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Project Cards Registry Table */}
          <div className="zyricon-glass-card rounded-2xl p-6 space-y-4 border border-white/[0.1]">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2.5">
                <FolderKanban className="w-5 h-5 text-white" />
                <h3 className="text-base font-semibold text-white">
                  Реестр созданных карточек проектов ({projects.length})
                </h3>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-zinc-400">
                <Lock className="w-3.5 h-3.5 text-[#C50337]" />
                <span>Допуск RBAC: {role}</span>
              </div>
            </div>

            {projects.length === 0 ? (
              <div className="text-sm text-zinc-400 py-6 text-center">
                Нет созданных карточек проектов для текущей роли ({role}).
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-white/[0.08] text-zinc-400 text-xs">
                      <th className="py-2.5 pr-3">Код</th>
                      <th className="py-2.5 px-3">Наименование проекта</th>
                      <th className="py-2.5 px-3">Исполнитель</th>
                      <th className="py-2.5 px-3">Гриф</th>
                      <th className="py-2.5 pl-3 text-right">Файл</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.06]">
                    {projects.map((p) => (
                      <tr key={p.id} className="hover:bg-white/[0.02]">
                        <td className="py-3 pr-3 font-mono text-xs text-zinc-300">
                          {p.module_code || "MOD"}
                        </td>
                        <td className="py-3 px-3">
                          <div className="font-medium text-white">{p.project_title}</div>
                          <div className="text-xs text-zinc-400 truncate max-w-xs">
                            {p.note_text}
                          </div>
                        </td>
                        <td className="py-3 px-3 text-zinc-300">
                          <div>{p.executor_name}</div>
                          <div className="text-xs text-zinc-500">{p.executor_department}</div>
                        </td>
                        <td className="py-3 px-3">
                          <span className="text-xs font-mono px-2.5 py-0.5 rounded uppercase bg-white/[0.07] text-zinc-200">
                            {p.access_level}
                          </span>
                        </td>
                        <td className="py-3 pl-3 text-right">
                          <button
                            onClick={() =>
                              void downloadGeneratedDocx(p.generated_file_name, token)
                            }
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.08] hover:bg-white/[0.15] text-xs text-white transition"
                          >
                            <Download className="w-3.5 h-3.5" />
                            <span>Скачать</span>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

import React, { useRef, useState } from "react";
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Download,
  FileCheck2,
  FileUp,
  GitMerge,
  Info,
  ShieldCheck,
  Wand2,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { checkDocxCompliance } from "../../services/apiClient";
import { ComplianceCheckResponse } from "../../types/api";

const RULES_SUMMARY = [
  { code: "CHK-01", text: "Удаление технической отметки «МОДУЛЬНЫЙ ДОКУМЕНТ»" },
  { code: "CHK-02", text: "Удаление верхнего грифа утверждения шаблона (УТВЕРЖДЕНО / УТВ-...)" },
  { code: "CHK-03", text: "Отсутствие незаполненных прочерков ____ и подсказок в скобках [Указать ...]" },
  { code: "CHK-04", text: "Удаление цифровых сносок шаблона [1]..[15]" },
  { code: "CHK-05", text: "Удаление справочного раздела «Примечания по заполнению»" },
  { code: "CHK-06", text: "Сохранность служебной зоны ДАТА / РЕГИСТРАЦИОННЫЙ НОМЕР (НЕ УДАЛЯТЬ)" },
  { code: "CHK-07", text: "Сохранность служебной зоны ВИЗУАЛИЗАЦИЯ ЭП (НЕ УДАЛЯТЬ)" },
  { code: "CHK-08", text: "Замена заглушки подписи «И. О. Фамилия» на реального подписанта" },
  { code: "CHK-09", text: "Наличие пункта о контроле за исполнением документа (п. 9.2.6, 9.7.6 ОД-184)" },
  { code: "CHK-10", text: "Наличие констатирующей части / преамбулы (п. 9.1.4 ОД-184)" },
  { code: "CHK-MARG", text: "Поля страницы: левое ≥ 30 мм, правое ≥ 15 мм, верх/низ ≥ 20 мм (п. 5.1 ОД-184)" },
  { code: "CHK-FONT", text: "Шрифт Times New Roman / Arial / PT Astra Serif, 12–14 pt (п. 5.2 ОД-184)" },
  { code: "CHK-LINE", text: "Межстрочный интервал: одинарный или полуторный 1.0–1.5 (п. 5.3 ОД-184)" },
  { code: "CHK-INDENT", text: "Абзацный отступ первой строки (красная строка) 1.25 см (п. 5.3 ОД-184)" },
  { code: "CHK-TITLE", text: "Заголовок к тексту («О ...» / «Об ...») без точки и без подчеркивания (п. 5.5 ОД-184)" },
  { code: "CHK-SIGN", text: "Реквизит «Подпись»: наименование должности, подпись/ЭП, ФИО (п. 6.1 ОД-184)" },
];

export const ComplianceScreen: React.FC = () => {
  const { token } = useAuth();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [result, setResult] = useState<ComplianceCheckResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [showRulesReference, setShowRulesReference] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const runCheck = async (file: File) => {
    setSelectedFile(file);
    setIsChecking(true);
    setErrorMsg(null);
    try {
      const res = await checkDocxCompliance(file, token);
      setResult(res);
    } catch (err: any) {
      setErrorMsg(err?.message || "Ошибка при проверке файла .docx");
    } finally {
      setIsChecking(false);
    }
  };

  return (
    <div className="flex-1 h-screen zyricon-stage-bg overflow-y-auto px-6 sm:px-12 py-10">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Top Title + Collapsible Rules Toggle */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-white">Проверка документа на ошибки</h1>
            <p className="text-sm text-zinc-400 mt-1">
              Быстрая проверка файла Word (.docx) на правильность оформления по инструкции
            </p>
          </div>

          <button
            onClick={() => setShowRulesReference((v) => !v)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#111115] hover:bg-white/[0.06] border border-white/[0.12] text-sm text-zinc-200 transition"
          >
            <ShieldCheck className="w-4 h-4 text-[#C50337]" />
            <span>Что проверяется ({RULES_SUMMARY.length} пунктов)</span>
            {showRulesReference ? (
              <ChevronUp className="w-4 h-4" />
            ) : (
              <ChevronDown className="w-4 h-4" />
            )}
          </button>
        </div>

        {/* Collapsible Rules Reference */}
        {showRulesReference && (
          <div className="zyricon-glass-card rounded-2xl p-5 grid grid-cols-1 sm:grid-cols-2 gap-2.5">
            {RULES_SUMMARY.map((r) => (
              <div
                key={r.code}
                className="flex items-start gap-2.5 text-xs p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.06]"
              >
                <span className="font-mono px-2 py-0.5 rounded bg-white/[0.08] text-white shrink-0">
                  {r.code}
                </span>
                <span className="text-zinc-300 leading-relaxed">{r.text}</span>
              </div>
            ))}
          </div>
        )}

        {/* Clean Centered Upload Dropzone */}
        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            const f = e.dataTransfer.files?.[0];
            if (f && f.name.endsWith(".docx")) {
              runCheck(f);
            } else {
              setErrorMsg("Пожалуйста, загрузите файл в формате .docx");
            }
          }}
          className="zyricon-glass-card rounded-2xl p-8 border-2 border-dashed border-white/[0.15] hover:border-white/[0.3] transition text-center cursor-pointer space-y-3"
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".docx"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) runCheck(f);
            }}
          />

          <div className="w-12 h-12 rounded-2xl bg-white/[0.05] border border-white/[0.1] flex items-center justify-center mx-auto text-zinc-300">
            <FileUp className="w-6 h-6" />
          </div>

          <div>
            <div className="text-base font-semibold text-white">
              Перетащите файл Word (.docx) сюда или нажмите для выбора
            </div>
            <p className="text-xs text-zinc-400 mt-1">
              Проверяется шрифт, поля, интервалы, реквизиты, подписи и отсутствие меток шаблона
            </p>
          </div>

          {selectedFile && (
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/[0.08] text-xs text-white border border-white/[0.15]">
              <FileCheck2 className="w-3.5 h-3.5 text-[#C50337]" />
              <span>{selectedFile.name}</span>
            </div>
          )}
        </div>

        {errorMsg && (
          <div className="p-4 rounded-xl bg-[#C50337]/20 border border-[#C50337]/50 text-sm text-white">
            {errorMsg}
          </div>
        )}

        {isChecking && (
          <div className="zyricon-glass-card rounded-2xl p-10 text-center space-y-4">
            <div className="w-10 h-10 rounded-full zyricon-orb animate-spin mx-auto" />
            <div className="text-sm font-semibold text-white">
              Выполняется проверка документа по правилам ОД-184...
            </div>
          </div>
        )}

        {/* Results */}
        {result && !isChecking && (
          <div className="space-y-4">
            {/* Score Banner with Auto-Fix Download Button */}
            <div className="zyricon-glass-card rounded-2xl p-5 border border-white/[0.12] flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div
                  className={`w-16 h-16 rounded-2xl flex items-center justify-center font-mono font-bold border ${
                    result.is_compliant
                      ? "bg-white/[0.08] border-white/[0.2] text-white"
                      : "bg-[#C50337]/20 border-[#C50337]/50 text-white"
                  }`}
                >
                  <span className="text-xl">{result.score_pct.toFixed(0)}%</span>
                </div>

                <div>
                  <span
                    className={`inline-block px-3 py-0.5 rounded-full text-xs font-semibold ${
                      result.is_compliant ? "bg-white/[0.12] text-white" : "bg-[#C50337] text-white"
                    }`}
                  >
                    {result.is_compliant ? "Проверка пройдена" : "Требует доработки"}
                  </span>
                  <h2 className="text-base font-semibold text-white mt-1.5">{result.file_name}</h2>
                  <div className="text-xs text-zinc-400 mt-0.5">
                    Вид: <strong className="text-zinc-200">{result.detected_doc_kind}</strong> • Пройдено: {result.passed_checks} из {result.total_checks} • Критических ошибок:{" "}
                    {result.critical_count}
                  </div>
                </div>
              </div>

              {result.fixed_file_url && (
                <a
                  href={result.fixed_file_url}
                  download
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/[0.08] hover:bg-white/[0.16] text-white border border-white/[0.2] transition-colors text-sm font-medium shrink-0"
                >
                  <Wand2 className="w-4 h-4 text-[#C50337]" />
                  <span>Скачать исправленный .DOCX</span>
                  <Download className="w-4 h-4 text-zinc-300 ml-1" />
                </a>
              )}
            </div>

            {/* Issues List */}
            {result.issues.length === 0 ? (
              <div className="p-5 rounded-2xl bg-[#111115] border border-white/[0.14] flex items-center gap-3 text-sm text-white">
                <CheckCircle2 className="w-5 h-5 text-white shrink-0" />
                <span>Нарушений не обнаружено. Документ готов к согласованию.</span>
              </div>
            ) : (
              <div className="space-y-3">
                {result.issues.map((iss, i) => {
                  const isCrit = iss.severity === "critical";
                  return (
                    <div
                      key={`${iss.rule_id}-${i}`}
                      className={`p-5 rounded-2xl border space-y-2 ${
                        isCrit
                          ? "bg-[#160D11] border-[#C50337]/50"
                          : "bg-[#111115] border-white/[0.12]"
                      }`}
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          {isCrit ? (
                            <AlertOctagon className="w-4 h-4 text-[#C50337]" />
                          ) : iss.severity === "warning" ? (
                            <AlertTriangle className="w-4 h-4 text-zinc-300" />
                          ) : (
                            <Info className="w-4 h-4 text-zinc-400" />
                          )}
                          <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-white/[0.08] text-white">
                            {iss.rule_id}
                          </span>
                          <span className="text-sm font-semibold text-white">{iss.title}</span>
                        </div>
                        <span className="text-xs font-mono text-zinc-400">{iss.clause_ref}</span>
                      </div>
                      <p className="text-sm text-zinc-300">{iss.description}</p>
                      <div className="text-xs text-zinc-200 pt-1">
                        <strong className="text-white">Рекомендация: </strong>
                        {iss.recommendation}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Approval Route */}
            {result.approval_recommendation && (
              <div className="zyricon-glass-card rounded-2xl p-5 space-y-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-semibold text-white flex items-center gap-2">
                    <GitMerge className="w-4 h-4 text-[#C50337]" />
                    Маршрут согласования (Правило № {result.approval_recommendation.rule_number})
                  </span>
                  <span className="text-zinc-400">
                    Подписант: <strong className="text-white">{result.approval_recommendation.signatory}</strong>
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-5 gap-2.5">
                  {result.approval_recommendation.stages.map((st) => (
                    <div
                      key={st.order}
                      className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.08] text-xs space-y-1"
                    >
                      <div className="font-mono text-zinc-400">Этап {st.order}</div>
                      <div className="font-semibold text-white">{st.department}</div>
                      <div className="text-zinc-400">{st.role_name}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

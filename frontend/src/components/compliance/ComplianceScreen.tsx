import React, { useRef, useState } from "react";
import {
  AlertOctagon,
  AlertTriangle,
  CheckCircle2,
  FileCheck2,
  FileUp,
  GitMerge,
  Info,
  ShieldCheck,
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
];

export const ComplianceScreen: React.FC = () => {
  const { token } = useAuth();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [result, setResult] = useState<ComplianceCheckResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
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
    <div className="flex-1 h-[calc(100vh-4rem)] zyricon-stage-bg overflow-y-auto px-6 sm:px-12 py-8 space-y-6">
      {/* Header */}
      <div className="max-w-6xl mx-auto">
        <div className="text-xs font-mono uppercase tracking-widest text-zinc-400">
          Автоматический нормоконтроль • Инструкция № ОД-184 и Раздел 3.3
        </div>
        <h1 className="text-2xl sm:text-3xl font-semibold text-white mt-1">
          Проверка черновика .DOCX (CHK-01 .. CHK-10)
        </h1>
      </div>

      {/* Main Grid */}
      <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Upload Zone + 10 Rules Reference */}
        <div className="lg:col-span-5 space-y-5">
          <div
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const f = e.dataTransfer.files?.[0];
              if (f) void runCheck(f);
            }}
            className="zyricon-glass-card rounded-2xl p-8 border-2 border-dashed border-white/[0.18] hover:border-[#C50337] cursor-pointer text-center space-y-4 transition"
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".docx"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void runCheck(f);
              }}
            />

            <div className="w-14 h-14 rounded-2xl bg-white/[0.06] border border-white/[0.12] mx-auto flex items-center justify-center">
              <FileUp className="w-6 h-6 text-white" />
            </div>

            <div>
              <div className="text-base font-semibold text-white">
                Перетащите черновик .DOCX сюда или выберите файл
              </div>
              <p className="text-sm text-zinc-400 mt-1.5 leading-relaxed">
                Система проверит документ на соблюдение 10 обязательных правил оформления и рассчитает маршрут визирования.
              </p>
            </div>

            {selectedFile && (
              <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-white/[0.08] text-xs font-mono text-white">
                <FileCheck2 className="w-4 h-4 text-[#C50337]" />
                <span>{selectedFile.name}</span>
              </div>
            )}
          </div>

          {errorMsg && (
            <div className="p-4 rounded-xl bg-[#C50337]/20 border border-[#C50337]/50 text-sm text-white">
              {errorMsg}
            </div>
          )}

          {/* 10 Rules Checklist Reference */}
          <div className="zyricon-glass-card rounded-2xl p-5 space-y-3">
            <div className="text-sm font-semibold text-white flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-zinc-300" />
              <span>Контрольные точки проверки (10 правил)</span>
            </div>
            <div className="space-y-2">
              {RULES_SUMMARY.map((r) => (
                <div
                  key={r.code}
                  className="flex items-start gap-2.5 text-sm p-2 rounded-lg bg-white/[0.02] border border-white/[0.06]"
                >
                  <span className="font-mono text-xs px-2 py-0.5 rounded bg-white/[0.08] text-white shrink-0">
                    {r.code}
                  </span>
                  <span className="text-zinc-300">{r.text}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Inspection Results */}
        <div className="lg:col-span-7 space-y-5">
          {isChecking ? (
            <div className="zyricon-glass-card rounded-2xl p-10 text-center space-y-4">
              <div className="w-12 h-12 rounded-full zyricon-orb animate-spin mx-auto" />
              <div className="text-base font-semibold text-white">
                Выполняется проверка .DOCX по 10 правилам ОД-184...
              </div>
            </div>
          ) : !result ? (
            <div className="zyricon-glass-card rounded-2xl p-10 text-center space-y-3 border border-white/[0.1]">
              <FileCheck2 className="w-12 h-12 text-zinc-500 mx-auto" />
              <div className="text-base font-semibold text-white">
                Ожидание загрузки файла .DOCX
              </div>
              <p className="text-sm text-zinc-400 max-w-md mx-auto leading-relaxed">
                Загрузите исходный шаблон из папки <span className="font-mono text-white">materials/</span> для демонстрации выявления нарушений или сгенерированный проект для подтверждения 100% соответствия.
              </p>
            </div>
          ) : (
            <div className="space-y-5">
              {/* Score Summary Banner */}
              <div className="zyricon-glass-card rounded-2xl p-6 border border-white/[0.14] space-y-5">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <div
                      className={`w-20 h-20 rounded-2xl flex flex-col items-center justify-center font-mono font-bold border ${
                        result.is_compliant
                          ? "bg-white/[0.08] border-white/[0.25] text-white"
                          : "bg-[#C50337]/20 border-[#C50337]/50 text-white"
                      }`}
                    >
                      <span className="text-2xl">{result.score_pct.toFixed(0)}%</span>
                      <span className="text-xs font-normal text-zinc-300">Индекс</span>
                    </div>

                    <div>
                      <div className="flex items-center gap-2.5">
                        <span
                          className={`px-3 py-1 rounded-full text-xs font-semibold ${
                            result.is_compliant
                              ? "bg-white/[0.1] text-white border border-white/[0.2]"
                              : "bg-[#C50337] text-white"
                          }`}
                        >
                          {result.is_compliant
                            ? "Соответствует требованиям ДОУ"
                            : "Требует доработки перед визированием"}
                        </span>
                        {result.detected_module_code && (
                          <span className="text-xs font-mono px-2.5 py-1 rounded bg-white/[0.08] text-zinc-200">
                            {result.detected_module_code}
                          </span>
                        )}
                      </div>
                      <h2 className="text-lg font-semibold text-white mt-1.5">
                        {result.file_name} • Вид: {result.detected_doc_kind}
                      </h2>
                    </div>
                  </div>
                </div>

                {/* Counters */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 border-t border-white/[0.08] text-sm">
                  <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                    <div className="text-xs text-zinc-400">Всего проверок</div>
                    <div className="text-lg font-semibold text-white font-mono mt-1">
                      {result.total_checks}
                    </div>
                  </div>
                  <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                    <div className="text-xs text-zinc-400">Пройдено</div>
                    <div className="text-lg font-semibold text-white font-mono mt-1">
                      {result.passed_checks}
                    </div>
                  </div>
                  <div className="p-3 rounded-xl bg-[#C50337]/15 border border-[#C50337]/40">
                    <div className="text-xs text-zinc-200">Критических ошибок</div>
                    <div className="text-lg font-semibold text-white font-mono mt-1">
                      {result.critical_count}
                    </div>
                  </div>
                  <div className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.08]">
                    <div className="text-xs text-zinc-400">Предупреждений</div>
                    <div className="text-lg font-semibold text-white font-mono mt-1">
                      {result.warning_count}
                    </div>
                  </div>
                </div>
              </div>

              {/* Issues List */}
              {result.issues.length === 0 ? (
                <div className="p-5 rounded-2xl bg-[#111115] border border-white/[0.16] flex items-center gap-3.5 text-sm text-white">
                  <CheckCircle2 className="w-5 h-5 text-white shrink-0" />
                  <span>
                    Нарушений не выявлено. Документ полностью соответствует Инструкции № ОД-184 и Разделу 3.3 Методических рекомендаций.
                  </span>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                    Выявленные замечания и рекомендации ({result.issues.length})
                  </div>
                  {result.issues.map((iss, i) => {
                    const isCrit = iss.severity === "critical";
                    return (
                      <div
                        key={`${iss.rule_id}-${i}`}
                        className={`p-5 rounded-2xl border space-y-2.5 ${
                          isCrit
                            ? "bg-[#160D11] border-[#C50337]/50"
                            : "bg-[#111115] border-white/[0.14]"
                        }`}
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2.5">
                            {isCrit ? (
                              <AlertOctagon className="w-4 h-4 text-[#C50337]" />
                            ) : iss.severity === "warning" ? (
                              <AlertTriangle className="w-4 h-4 text-zinc-300" />
                            ) : (
                              <Info className="w-4 h-4 text-zinc-400" />
                            )}
                            <span className="text-xs font-mono font-bold px-2.5 py-0.5 rounded bg-white/[0.08] text-white">
                              {iss.rule_id}
                            </span>
                            <span className="text-sm font-semibold text-white">{iss.title}</span>
                          </div>
                          <span className="text-xs font-mono px-2.5 py-0.5 rounded bg-white/[0.06] text-zinc-300">
                            Норма: {iss.clause_ref}
                          </span>
                        </div>

                        <p className="text-sm text-zinc-300 leading-relaxed">{iss.description}</p>

                        <div className="p-3 rounded-xl bg-black/50 border border-white/[0.08] text-sm text-zinc-200">
                          <strong className="text-white">Рекомендация: </strong>
                          {iss.recommendation}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Recommended Approval Route */}
              {result.approval_recommendation && (
                <div className="zyricon-glass-card rounded-2xl p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold text-white flex items-center gap-2">
                      <GitMerge className="w-4 h-4 text-[#C50337]" />
                      <span>
                        Маршрут визирования (Правило № {result.approval_recommendation.rule_number})
                      </span>
                    </div>
                    <span className="text-sm text-zinc-300">
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
                        <div className="font-semibold text-white text-sm">{st.department}</div>
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
    </div>
  );
};

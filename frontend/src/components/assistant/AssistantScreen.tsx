import React, { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  BookMarked,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  Download,
  FileSpreadsheet,
  FileText,
  GitMerge,
  HelpCircle,
  Layers,
  Paperclip,
  Radio,
  ShieldAlert,
  Terminal,
  Wand2,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import {
  downloadGeneratedDocx,
  sendAssistantQuery,
  streamAssistantQuery,
} from "../../services/apiClient";
import {
  ApprovalRecommendation,
  DetectedTermRef,
  DocumentGenerateResponse,
  QueryResponse,
  ScreenId,
  SourceRef,
} from "../../types/api";

interface AssistantScreenProps {
  sessionId: string;
  onResetSession: () => void;
  onNavigateScreen: (screen: ScreenId, templateCode?: string) => void;
}

interface ChatTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  isStreaming?: boolean;
  responseMeta?: Partial<QueryResponse>;
}

const QUICK_SCENARIOS = [
  {
    id: "clause-9-14",
    badge: "п. 9.14 ОД-184",
    title: "Особое мнение при подписании акта",
    prompt: "Как оформляется особое мнение и отказ от подписания акта согласно инструкции?",
  },
  {
    id: "branch-2-3",
    badge: "Правила № 2 / 3",
    title: "Согласование приема-передачи дел",
    prompt: "С кем согласовать приказ о приеме и передаче дел и имущества?",
  },
  {
    id: "dialog-doc-utv01",
    badge: "Шаблон УТВ-01",
    title: "Заполнить приказ о вводе ИС в чате",
    prompt: "Помоги заполнить приказ о вводе в эксплуатацию информационной системы",
  },
  {
    id: "table-utv06",
    badge: "Шаблон УТВ-06",
    title: "Состав проектного комитета",
    prompt: "Какие роли входят в состав проектного комитета в модульном распоряжении?",
  },
  {
    id: "terms-medo",
    badge: "Глоссарий",
    title: "Термины МЭДО и ИОД",
    prompt: "Что такое МЭДО и ИОД в инструкции по документообороту?",
  },
  {
    id: "zero-hallucination",
    badge: "Контроль БЗ",
    title: "Вопрос вне регламента",
    prompt: "Как оформить корпоративную подписку на фитнес-клуб и бассейн?",
  },
];

export const AssistantScreen: React.FC<AssistantScreenProps> = ({
  sessionId,
  onResetSession,
  onNavigateScreen,
}) => {
  const { role, token } = useAuth();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [useSseStream, setUseSseStream] = useState(false);
  const [expandedSourceKey, setExpandedSourceKey] = useState<string | null>(null);
  const [copiedNoteId, setCopiedNoteId] = useState<string | null>(null);

  const chatEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setTurns([]);
  }, [sessionId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, isLoading]);

  const handleSendQuery = async (customQuery?: string) => {
    const queryText = (customQuery ?? inputText).trim();
    if (!queryText || isLoading) return;

    if (queryText.startsWith("Открыть конструктор шаблона ")) {
      const code = queryText.replace("Открыть конструктор шаблона ", "").trim();
      onNavigateScreen("constructor", code);
      return;
    }

    if (!customQuery) {
      setInputText("");
    }

    const userTurnId = crypto.randomUUID();
    const assistantTurnId = crypto.randomUUID();
    const historyPayload = turns.map((t) => ({
      role: t.role,
      content: t.content,
    }));

    const userTurn: ChatTurn = {
      id: userTurnId,
      role: "user",
      content: queryText,
      timestamp: new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }),
    };

    setTurns((prev) => [...prev, userTurn]);
    setIsLoading(true);

    const lastTurn = turns[turns.length - 1];
    const isSlotFillingTurn =
      Boolean(lastTurn?.responseMeta?.slot_filling_state?.active) ||
      /заполн|сформируй|создай проект|подготовь приказ/i.test(queryText);

    if (useSseStream && !isSlotFillingTurn) {
      const placeholderTurn: ChatTurn = {
        id: assistantTurnId,
        role: "assistant",
        content: "",
        timestamp: new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }),
        isStreaming: true,
        responseMeta: {},
      };
      setTurns((prev) => [...prev, placeholderTurn]);

      try {
        await streamAssistantQuery(
          {
            query: queryText,
            user_role: role,
            session_id: sessionId,
            history: historyPayload,
            top_k: 5,
          },
          token,
          {
            onMetadata: (meta) => {
              setTurns((prev) =>
                prev.map((t) =>
                  t.id === assistantTurnId
                    ? { ...t, responseMeta: { ...t.responseMeta, ...meta } }
                    : t
                )
              );
            },
            onToken: (chunk) => {
              setTurns((prev) =>
                prev.map((t) =>
                  t.id === assistantTurnId ? { ...t, content: t.content + chunk } : t
                )
              );
            },
            onDone: (finalInfo) => {
              setTurns((prev) =>
                prev.map((t) =>
                  t.id === assistantTurnId
                    ? {
                        ...t,
                        isStreaming: false,
                        responseMeta: {
                          ...t.responseMeta,
                          latency_ms: finalInfo.latency_ms,
                          zero_hallucination_triggered:
                            finalInfo.zero_hallucination_triggered ??
                            t.responseMeta?.zero_hallucination_triggered,
                        },
                      }
                    : t
                )
              );
            },
          }
        );
      } catch (err: any) {
        setTurns((prev) =>
          prev.map((t) =>
            t.id === assistantTurnId
              ? {
                  ...t,
                  isStreaming: false,
                  content: `Ошибка обращения к серверу: ${err?.message || "Неизвестная ошибка"}`,
                }
              : t
          )
        );
      } finally {
        setIsLoading(false);
      }
    } else {
      try {
        const res = await sendAssistantQuery(
          {
            query: queryText,
            user_role: role,
            session_id: sessionId,
            history: historyPayload,
            top_k: 5,
          },
          token
        );

        const assistantTurn: ChatTurn = {
          id: assistantTurnId,
          role: "assistant",
          content: res.answer,
          timestamp: new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }),
          responseMeta: res,
        };
        setTurns((prev) => [...prev, assistantTurn]);
      } catch (err: any) {
        const errTurn: ChatTurn = {
          id: assistantTurnId,
          role: "assistant",
          content: `Сервер бэкенда (порт 8000) не запущен или недоступен: ${err?.message || ""}`,
          timestamp: new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }),
        };
        setTurns((prev) => [...prev, errTurn]);
      } finally {
        setIsLoading(false);
      }
    }
  };

  const renderApprovalTimeline = (rec: ApprovalRecommendation) => (
    <div className="mt-4 p-5 rounded-2xl bg-[#111115] border border-white/[0.12] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.08] pb-3">
        <div className="flex items-center gap-2.5">
          <GitMerge className="w-5 h-5 text-[#C50337]" />
          <span className="text-base font-semibold text-white">
            Маршрут визирования • Правило № {rec.rule_number}
          </span>
          <span className="text-xs px-2.5 py-1 rounded-md bg-white/[0.07] text-zinc-200 border border-white/[0.1]">
            {rec.doc_type_name}
          </span>
        </div>
        <button
          onClick={() => onNavigateScreen("constructor")}
          className="text-xs font-medium px-3.5 py-1.5 rounded-lg bg-white/[0.08] hover:bg-white/[0.14] text-white border border-white/[0.12] transition"
        >
          Открыть в конструкторе шаблонов →
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {rec.stages.map((st) => (
          <div
            key={`${st.order}-${st.role_name}`}
            className="p-3.5 rounded-xl bg-white/[0.03] border border-white/[0.08] flex flex-col justify-between space-y-2"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-white/[0.08] text-white font-semibold">
                Этап {st.order}
              </span>
              <span className="text-xs text-zinc-400">Обязательно</span>
            </div>
            <div>
              <div className="text-sm font-semibold text-white leading-snug">{st.department}</div>
              <div className="text-xs text-zinc-300 mt-1">{st.role_name}</div>
            </div>
            <div className="text-xs text-zinc-500 leading-tight pt-2 border-t border-white/[0.06]">
              {st.reason}
            </div>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between text-sm pt-1 text-zinc-300">
        <span>
          Утверждающее лицо (Подписант):{" "}
          <strong className="text-white font-semibold">{rec.signatory}</strong>
        </span>
        <span className="text-xs text-zinc-500">Раздел 4.2 Методических рекомендаций</span>
      </div>
    </div>
  );

  const renderGeneratedDocumentCard = (
    doc: DocumentGenerateResponse,
    slotState?: Record<string, any> | null
  ) => (
    <div className="mt-4 p-5 rounded-2xl bg-[#111115] border border-white/[0.16] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-[#C50337]/20 border border-[#C50337]/40 flex items-center justify-center">
            <CheckCircle2 className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="text-base font-semibold text-white">
              Проект документа сформирован ({slotState?.reg_number || "Модульный шаблон"})
            </div>
            <div className="text-xs text-zinc-400 font-mono mt-0.5">{doc.file_name}</div>
          </div>
        </div>

        <button
          onClick={() => void downloadGeneratedDocx(doc.file_name, token)}
          className="px-4 py-2.5 rounded-xl bg-[#C50337] hover:opacity-90 text-white text-sm font-semibold flex items-center gap-2 transition"
        >
          <Download className="w-4 h-4" />
          <span>Скачать проект .DOCX</span>
        </button>
      </div>

      <div className="p-3.5 rounded-xl bg-black/50 border border-white/[0.08] flex items-center justify-between gap-3">
        <div className="text-sm text-zinc-200">
          <span className="text-zinc-400">Обязательная отметка п. 2.3: </span>
          <span className="font-mono text-white">{doc.note_text}</span>
        </div>
        <button
          onClick={() => {
            navigator.clipboard?.writeText(doc.note_text);
            setCopiedNoteId(doc.project_id);
            setTimeout(() => setCopiedNoteId(null), 1800);
          }}
          className="px-3 py-1.5 rounded-lg bg-white/[0.08] hover:bg-white/[0.14] text-xs text-white shrink-0 flex items-center gap-1.5"
        >
          <Copy className="w-3.5 h-3.5" />
          <span>{copiedNoteId === doc.project_id ? "Скопировано" : "Копировать"}</span>
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex-1 h-[calc(100vh-4rem)] zyricon-stage-bg flex flex-col justify-between overflow-hidden relative">
      {/* Main Scrollable Stage */}
      <div className="flex-1 overflow-y-auto px-6 sm:px-12 py-8">
        {turns.length === 0 ? (
          /* SERIOUS EXECUTIVE EMPTY STATE (Large scale, strict 3-color palette) */
          <div className="max-w-5xl mx-auto min-h-full flex flex-col items-center justify-center space-y-9 py-4">
            {/* Sphere + Executive Title */}
            <div className="flex flex-col items-center text-center space-y-5">
              <div className="w-20 h-20 rounded-full zyricon-orb flex items-center justify-center">
                <div className="w-14 h-14 rounded-full bg-gradient-to-tr from-black/70 via-transparent to-white/25" />
              </div>

              <div className="space-y-2.5">
                <div className="text-xs font-mono uppercase tracking-widest text-zinc-400">
                  Центр документационного обеспечения • Банк России
                </div>
                <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight text-white">
                  Интеллектуальный помощник по регламентам ДОУ
                </h1>
                <p className="text-base text-zinc-400 max-w-2xl mx-auto leading-relaxed">
                  Формулируйте рабочие задачи своими словами: система определит точные положения Инструкции № ОД-184, рассчитает маршрут согласования и подготовит проект документа по шаблону.
                </p>
              </div>
            </div>

            {/* Central Input & Scenario Pills */}
            <div className="w-full max-w-4xl space-y-4">
              {/* Quick Scenarios Row */}
              <div className="flex flex-wrap items-center justify-center gap-2.5">
                {QUICK_SCENARIOS.map((sc) => (
                  <button
                    key={sc.id}
                    onClick={() => void handleSendQuery(sc.prompt)}
                    className="inline-flex items-center gap-2.5 px-4 py-2 rounded-full bg-[#111115] hover:bg-white/[0.08] border border-white/[0.12] hover:border-white/[0.28] text-sm text-zinc-200 transition"
                  >
                    <span className="text-xs font-mono px-2 py-0.5 rounded bg-white/[0.08] text-zinc-300">
                      {sc.badge}
                    </span>
                    <span className="font-medium text-white">{sc.title}</span>
                  </button>
                ))}
              </div>

              {/* Large Serious Input Box */}
              <div className="zyricon-input-box rounded-2xl p-5 space-y-4 transition">
                <textarea
                  rows={3}
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void handleSendQuery();
                    }
                  }}
                  placeholder="Введите вопрос по Инструкции № ОД-184, Матрице визирования или напишите «Помоги заполнить приказ о вводе в эксплуатацию ИС»..."
                  className="w-full bg-transparent text-base text-white placeholder-zinc-500 focus:outline-none resize-none leading-relaxed"
                />

                <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-white/[0.08]">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <button
                      type="button"
                      onClick={() => onNavigateScreen("compliance")}
                      className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] border border-white/[0.08] text-sm text-zinc-200 transition"
                    >
                      <Paperclip className="w-4 h-4 text-zinc-400" />
                      <span>Проверить черновик .DOCX</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setUseSseStream((s) => !s)}
                      className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm border transition ${
                        useSseStream
                          ? "bg-[#C50337]/20 text-white border-[#C50337]/50"
                          : "bg-white/[0.05] text-zinc-300 border-white/[0.08]"
                      }`}
                    >
                      <Radio className="w-4 h-4" />
                      <span>{useSseStream ? "Потоковый режим (SSE)" : "Полный режим диалога + DOCX"}</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => onNavigateScreen("constructor")}
                      className="hidden sm:inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] border border-white/[0.08] text-sm text-zinc-200 transition"
                    >
                      <Layers className="w-4 h-4 text-zinc-400" />
                      <span>Модульные шаблоны (7)</span>
                    </button>
                  </div>

                  <button
                    type="button"
                    disabled={!inputText.trim() || isLoading}
                    onClick={() => void handleSendQuery()}
                    className="px-5 py-2.5 rounded-xl bg-[#C50337] hover:opacity-90 disabled:opacity-35 flex items-center gap-2 text-sm font-semibold text-white transition"
                  >
                    <span>Отправить</span>
                    <ArrowUp className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            {/* Bottom 3 Architectural Cards (Zyricon Layout, Serious Scale) */}
            <div className="w-full max-w-4xl grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
              <div className="zyricon-glass-card rounded-2xl p-5 flex flex-col justify-between space-y-4 transition">
                <div className="flex items-center justify-between">
                  <div className="w-10 h-10 rounded-xl bg-white/[0.06] border border-white/[0.1] flex items-center justify-center">
                    <FileSpreadsheet className="w-5 h-5 text-white" />
                  </div>
                  <button
                    onClick={() => onNavigateScreen("constructor")}
                    className="px-3 py-1.5 rounded-lg bg-white/[0.08] hover:bg-white/[0.15] border border-white/[0.12] text-xs font-medium text-white transition"
                  >
                    Открыть
                  </button>
                </div>
                <div>
                  <h3 className="text-base font-semibold text-white">Конструктор УТВ-01..07</h3>
                  <p className="text-sm text-zinc-400 mt-1.5 leading-relaxed">
                    Автоматическое формирование проектов приказов и распоряжений по правилам Раздела 3.3.
                  </p>
                </div>
              </div>

              <div className="zyricon-glass-card rounded-2xl p-5 flex flex-col justify-between space-y-4 transition">
                <div className="flex items-center justify-between">
                  <div className="w-10 h-10 rounded-xl bg-white/[0.06] border border-white/[0.1] flex items-center justify-center">
                    <Wand2 className="w-5 h-5 text-white" />
                  </div>
                  <button
                    onClick={() => onNavigateScreen("compliance")}
                    className="px-3 py-1.5 rounded-lg bg-white/[0.08] hover:bg-white/[0.15] border border-white/[0.12] text-xs font-medium text-white transition"
                  >
                    Проверить
                  </button>
                </div>
                <div>
                  <h3 className="text-base font-semibold text-white">Нормоконтроль .DOCX</h3>
                  <p className="text-sm text-zinc-400 mt-1.5 leading-relaxed">
                    Проверка готовых документов по 10 правилам ОД-184 с выдачей рекомендаций по доработке.
                  </p>
                </div>
              </div>

              <div className="zyricon-glass-card rounded-2xl p-5 flex flex-col justify-between space-y-4 transition">
                <div className="flex items-center justify-between">
                  <div className="w-10 h-10 rounded-xl bg-white/[0.06] border border-white/[0.1] flex items-center justify-center">
                    <Terminal className="w-5 h-5 text-white" />
                  </div>
                  <button
                    onClick={() => onNavigateScreen("governance")}
                    className="px-3 py-1.5 rounded-lg bg-white/[0.08] hover:bg-white/[0.15] border border-white/[0.12] text-xs font-medium text-white transition"
                  >
                    Управление
                  </button>
                </div>
                <div>
                  <h3 className="text-base font-semibold text-white">Версионирование и ИБ</h3>
                  <p className="text-sm text-zinc-400 mt-1.5 leading-relaxed">
                    Горячее обновление регламентов без остановки сервиса, Матрица визирования и журнал аудита.
                  </p>
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* ACTIVE CONVERSATION VIEW (Large readable typography) */
          <div className="max-w-4xl mx-auto space-y-6 pb-8">
            <div className="flex items-center justify-between border-b border-white/[0.08] pb-4">
              <div className="flex items-center gap-2.5 text-sm text-zinc-400">
                <span className="w-2 h-2 rounded-full bg-[#C50337]" />
                <span>Рабочая сессия диалога:</span>
                <span className="font-mono text-zinc-200">{sessionId.slice(0, 8)}</span>
              </div>
              <button
                onClick={onResetSession}
                className="px-3.5 py-1.5 rounded-xl bg-white/[0.06] hover:bg-white/[0.12] text-sm text-white border border-white/[0.1] transition"
              >
                Новый диалог
              </button>
            </div>

            {turns.map((turn) => {
              if (turn.role === "user") {
                return (
                  <div key={turn.id} className="flex justify-end">
                    <div className="max-w-2xl rounded-2xl rounded-tr-sm px-5 py-4 bg-[#C50337] text-white text-base shadow-lg">
                      <div className="whitespace-pre-wrap leading-relaxed">{turn.content}</div>
                      <div className="text-xs text-white/75 text-right mt-1.5">{turn.timestamp}</div>
                    </div>
                  </div>
                );
              }

              const meta = turn.responseMeta;
              const sources: SourceRef[] = meta?.sources || [];
              const terms: DetectedTermRef[] = meta?.detected_terms || [];
              const approvalRec = meta?.approval_recommendation;
              const needsClarif = meta?.needs_clarification;
              const clarifQ = meta?.clarification_question;
              const quickReplies = meta?.quick_replies || [];
              const generatedDoc = meta?.generated_document;
              const zeroHallucination = meta?.zero_hallucination_triggered;

              return (
                <div
                  key={turn.id}
                  className="zyricon-glass-card rounded-2xl p-6 space-y-5 border border-white/[0.12]"
                >
                  {/* Top status bar */}
                  <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.08] pb-3.5">
                    <div className="flex items-center gap-3">
                      <div className="w-7 h-7 rounded-full zyricon-orb" />
                      <span className="text-base font-semibold text-white">Консультант ЦДО</span>
                      {typeof meta?.relevance_score === "number" && (
                        <span className="text-xs font-mono px-2.5 py-1 rounded-md bg-white/[0.07] text-zinc-200 border border-white/[0.12]">
                          Релевантность: {meta.relevance_score.toFixed(1)}%
                        </span>
                      )}
                    </div>

                    {zeroHallucination && (
                      <div className="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-[#C50337]/20 border border-[#C50337]/50 text-xs font-semibold text-white">
                        <ShieldAlert className="w-4 h-4 text-[#C50337]" />
                        <span>Zero-Hallucination Guard: вопрос вне регламентов ДОУ</span>
                      </div>
                    )}
                  </div>

                  {/* Answer text */}
                  <div className="text-base text-zinc-100 leading-relaxed whitespace-pre-wrap">
                    {turn.content || (turn.isStreaming ? "Формирование ответа по нормативной базе..." : "")}
                  </div>

                  {/* Interactive Clarification Box */}
                  {needsClarif && (
                    <div className="p-4 rounded-2xl bg-[#141419] border border-[#C50337]/50 space-y-3">
                      <div className="flex items-start gap-2.5">
                        <HelpCircle className="w-5 h-5 text-[#C50337] shrink-0 mt-0.5" />
                        <div className="text-sm font-medium text-white leading-relaxed">
                          {clarifQ || "Уточните параметр для точного определения маршрута или шаблона:"}
                        </div>
                      </div>

                      {quickReplies.length > 0 && (
                        <div className="flex flex-wrap gap-2.5 pt-1">
                          {quickReplies.map((replyText, idx) => (
                            <button
                              key={idx}
                              disabled={isLoading}
                              onClick={() => void handleSendQuery(replyText)}
                              className="px-4 py-2 rounded-xl bg-[#C50337] hover:opacity-90 text-sm font-medium text-white transition text-left"
                            >
                              {replyText}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Generated Document in Chat */}
                  {generatedDoc && renderGeneratedDocumentCard(generatedDoc, meta?.slot_filling_state)}

                  {/* Approval Route Timeline */}
                  {approvalRec && renderApprovalTimeline(approvalRec)}

                  {/* Detected Corporate Terms */}
                  {terms.length > 0 && (
                    <div className="space-y-2 pt-2">
                      <div className="text-xs font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
                        <BookMarked className="w-4 h-4 text-zinc-300" />
                        <span>Нормативные термины и сокращения ({terms.length})</span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {terms.map((term, i) => (
                          <div
                            key={`${term.canonical}-${i}`}
                            className="p-3.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-sm"
                          >
                            <div className="font-semibold text-white">
                              {term.canonical} — <span className="text-zinc-300">{term.expansion}</span>
                            </div>
                            {term.definition && (
                              <div className="text-xs text-zinc-400 mt-1">{term.definition}</div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Normative Sources List */}
                  {sources.length > 0 && (
                    <div className="space-y-3 pt-3 border-t border-white/[0.08]">
                      <div className="text-xs font-semibold uppercase tracking-wider text-zinc-400 flex items-center gap-2">
                        <FileText className="w-4 h-4 text-zinc-300" />
                        <span>Источники нормативной базы ({sources.length})</span>
                      </div>

                      <div className="space-y-2.5">
                        {sources.map((src, idx) => {
                          const srcKey = `${turn.id}-src-${idx}`;
                          const isExpanded = expandedSourceKey === srcKey;
                          const edition = src.version || src.edition || "1.0";
                          return (
                            <div
                              key={srcKey}
                              className="p-4 rounded-xl bg-[#111115] border border-white/[0.09] space-y-2.5"
                            >
                              <div className="flex flex-wrap items-center justify-between gap-2">
                                <div className="flex flex-wrap items-center gap-2.5 text-sm">
                                  <span className="px-2.5 py-0.5 rounded bg-white/[0.08] text-white font-mono font-semibold">
                                    {src.document_code} (ред. {edition})
                                  </span>
                                  {src.clause && (
                                    <span className="px-2.5 py-0.5 rounded bg-[#C50337]/20 border border-[#C50337]/40 text-white font-semibold">
                                      Пункт {src.clause}
                                    </span>
                                  )}
                                  {src.chapter && (
                                    <span className="text-zinc-400 truncate max-w-md">{src.chapter}</span>
                                  )}
                                </div>

                                <div className="flex items-center gap-2.5">
                                  <span className="text-xs font-mono px-2.5 py-1 rounded bg-white/[0.06] text-zinc-200 border border-white/[0.1]">
                                    {src.relevance_pct.toFixed(1)}%
                                  </span>
                                  {src.full_content && (
                                    <button
                                      onClick={() =>
                                        setExpandedSourceKey(isExpanded ? null : srcKey)
                                      }
                                      className="text-xs px-3 py-1 rounded-lg bg-white/[0.08] hover:bg-white/[0.14] text-white flex items-center gap-1.5 transition"
                                    >
                                      <span>{isExpanded ? "Скрыть полный текст" : "Полный текст пункта"}</span>
                                      {isExpanded ? (
                                        <ChevronUp className="w-3.5 h-3.5" />
                                      ) : (
                                        <ChevronDown className="w-3.5 h-3.5" />
                                      )}
                                    </button>
                                  )}
                                </div>
                              </div>

                              <p className="text-sm text-zinc-300 border-l-2 border-[#C50337] pl-3 leading-relaxed">
                                «{src.quote}»
                              </p>

                              {isExpanded && src.full_content && (
                                <div className="p-3.5 rounded-xl bg-black/50 border border-white/[0.08] text-sm text-zinc-200 whitespace-pre-wrap leading-relaxed">
                                  {src.full_content}
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* Footer Timings */}
                  <div className="flex flex-wrap items-center justify-between gap-2 pt-3 border-t border-white/[0.06] text-xs text-zinc-500 font-mono">
                    <div className="flex items-center gap-4">
                      <span className="flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5" />
                        Всего: {meta?.latency_ms ?? 0} мс
                      </span>
                      {typeof meta?.t_retriever_ms === "number" && (
                        <span>Поиск RRF: {meta.t_retriever_ms} мс</span>
                      )}
                      {typeof meta?.t_llm_ms === "number" && <span>LLM: {meta.t_llm_ms} мс</span>}
                    </div>
                    <span>Роль RBAC: {role}</span>
                  </div>
                </div>
              );
            })}

            {isLoading && (
              <div className="zyricon-glass-card rounded-2xl p-5 flex items-center gap-3.5 text-sm text-zinc-200">
                <div className="w-6 h-6 rounded-full zyricon-orb animate-spin shrink-0" />
                <span>
                  Поиск по Инструкции № ОД-184, сверка с Матрицей визирования и генерация ответа...
                </span>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>
        )}
      </div>

      {/* Bottom Sticky Input Bar when conversation is active */}
      {turns.length > 0 && (
        <div className="px-6 sm:px-12 py-4 bg-[#08080A]/95 backdrop-blur-xl border-t border-white/[0.08]">
          <div className="max-w-4xl mx-auto space-y-2.5">
            <div className="flex flex-wrap gap-2">
              {QUICK_SCENARIOS.slice(0, 4).map((sc) => (
                <button
                  key={sc.id}
                  disabled={isLoading}
                  onClick={() => void handleSendQuery(sc.prompt)}
                  className="text-xs px-3 py-1.5 rounded-full bg-[#111115] hover:bg-white/[0.08] border border-white/[0.1] text-zinc-300 transition"
                >
                  {sc.badge}: {sc.title}
                </button>
              ))}
            </div>

            <div className="zyricon-input-box rounded-2xl p-3 flex items-center gap-3">
              <input
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void handleSendQuery();
                  }
                }}
                placeholder="Введите уточняющий вопрос или реквизиты документа..."
                className="flex-1 bg-transparent text-base text-white placeholder-zinc-500 focus:outline-none px-2"
              />
              <button
                disabled={!inputText.trim() || isLoading}
                onClick={() => void handleSendQuery()}
                className="px-4 py-2 rounded-xl bg-[#C50337] hover:opacity-90 disabled:opacity-35 flex items-center gap-2 text-sm font-semibold text-white transition shrink-0"
              >
                <span>Отправить</span>
                <ArrowUp className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

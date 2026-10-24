import React, { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Copy,
  Download,
  FileText,
  GitMerge,
  HelpCircle,
  ShieldAlert,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import {
  downloadGeneratedDocx,
  sendAssistantQuery,
} from "../../services/apiClient";
import {
  ApprovalRecommendation,
  ChatTurn,
  DetectedTermRef,
  DocumentGenerateResponse,
  ScreenId,
  SourceRef,
} from "../../types/api";

interface AssistantScreenProps {
  sessionId: string;
  turns: ChatTurn[];
  onUpdateTurns: (sessionId: string, updater: (prev: ChatTurn[]) => ChatTurn[]) => void;
  onResetSession: () => void;
  onNavigateScreen: (screen: ScreenId, templateCode?: string) => void;
}

const QUICK_SCENARIOS = [
  {
    id: "clause-9-14",
    title: "Особое мнение при подписании акта",
    prompt: "Как оформляется особое мнение и отказ от подписания акта согласно инструкции?",
  },
  {
    id: "branch-2-3",
    title: "Согласование приема-передачи дел",
    prompt: "С кем согласовать приказ о приеме и передаче дел и имущества?",
  },
  {
    id: "dialog-doc-utv01",
    title: "Заполнить приказ о вводе ИС (УТВ-01)",
    prompt: "Помоги заполнить приказ о вводе в эксплуатацию информационной системы",
  },
  {
    id: "zero-hallucination",
    title: "Вопрос вне регламента (проверка защиты)",
    prompt: "Как оформить корпоративную подписку на фитнес-клуб и бассейн?",
  },
];

/**
 * Realistic 3D Red Planet SVG component with volcanic maria plains,
 * craters, atmospheric Fresnel rim light, and crescent terminator shadow.
 */
const HERO_TYPING_PHRASES: Array<{
  text: string;
  fontStyle: React.CSSProperties;
  className: string;
}> = [
  {
    text: "Чем могу помочь?",
    fontStyle: { fontFamily: "'IBM Plex Sans', 'Golos Text', system-ui, sans-serif" },
    className: "text-4xl sm:text-5xl font-bold tracking-tight",
  },
  {
    text: "Проверим документ по ОД-184?",
    fontStyle: { fontFamily: "'Playfair Display', Georgia, 'Times New Roman', serif" },
    className: "text-4xl sm:text-5xl italic font-semibold tracking-normal",
  },
  {
    text: "Рассчитаем маршрут визирования?",
    fontStyle: { fontFamily: "'JetBrains Mono', Consolas, 'Courier New', monospace" },
    className: "text-3xl sm:text-4xl font-semibold tracking-tight",
  },
  {
    text: "Соберем приказ по шаблону УТВ?",
    fontStyle: { fontFamily: "'Unbounded', 'Segoe UI', sans-serif" },
    className: "text-3xl sm:text-4xl font-semibold uppercase tracking-wider",
  },
  {
    text: "Найдем точный пункт регламента?",
    fontStyle: { fontFamily: "'Cormorant Garamond', Georgia, serif" },
    className: "text-4xl sm:text-5xl font-bold tracking-wide",
  },
];

const TypewriterHeroHeading: React.FC = () => {
  const [phraseIdx, setPhraseIdx] = useState(0);
  const [displayedText, setDisplayedText] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    const currentPhrase = HERO_TYPING_PHRASES[phraseIdx].text;

    if (!isDeleting && displayedText === currentPhrase) {
      const pauseTimer = window.setTimeout(() => {
        setIsDeleting(true);
      }, 2100);
      return () => window.clearTimeout(pauseTimer);
    }

    if (isDeleting && displayedText === "") {
      setIsDeleting(false);
      setPhraseIdx((prev) => (prev + 1) % HERO_TYPING_PHRASES.length);
      return;
    }

    const stepDelay = isDeleting ? 28 : 55;
    const timer = window.setTimeout(() => {
      const nextLength = isDeleting ? displayedText.length - 1 : displayedText.length + 1;
      setDisplayedText(currentPhrase.slice(0, nextLength));
    }, stepDelay);

    return () => window.clearTimeout(timer);
  }, [displayedText, isDeleting, phraseIdx]);

  const activeConfig = HERO_TYPING_PHRASES[phraseIdx];

  return (
    <div className="min-h-[3.75rem] sm:min-h-[4.25rem] flex items-center justify-center px-2">
      <h1
        style={activeConfig.fontStyle}
        className={`${activeConfig.className} text-white transition-all duration-150 text-center`}
      >
        <span>{displayedText}</span>
        <span className="inline-block w-[3px] h-[0.9em] bg-[#C50337] ml-1.5 align-middle animate-pulse" />
      </h1>
    </div>
  );
};

/**
 * 3D Mars Globe in rich Red/Crimson shades
 */
const MarsMapTile: React.FC<{ offsetX: number }> = ({ offsetX }) => (
  <g transform={`translate(${offsetX}, 0)`}>
    {/* Dark Iron-Oxide Maria (Syrtis Major, Acidalia Planitia, Mare Erythraeum) */}
    <path
      d="M 10 72 Q 38 58, 66 70 T 124 65 Q 158 56, 190 72 L 195 108 Q 162 122, 128 106 T 62 114 Q 30 120, 8 104 Z"
      fill="#450A0A"
      fillOpacity="0.62"
    />
    <path
      d="M 0 112 Q 35 102, 72 118 T 142 110 Q 172 104, 200 112 L 200 148 Q 165 158, 130 142 T 58 150 Q 25 154, 0 148 Z"
      fill="#2A0404"
      fillOpacity="0.58"
    />
    {/* Syrtis Major triangular dark shield */}
    <path
      d="M 82 54 L 106 88 L 70 96 Z"
      fill="#3B0404"
      fillOpacity="0.68"
    />
    {/* Northern Acidalia dark basin */}
    <ellipse cx="148" cy="52" rx="28" ry="14" fill="#3B0404" fillOpacity="0.55" />

    {/* Bright Scarlet/Crimson Dust Highlands (Tharsis & Arabia Terra) */}
    <ellipse cx="46" cy="76" rx="32" ry="18" fill="#EF4444" fillOpacity="0.38" />
    <ellipse cx="136" cy="96" rx="34" ry="16" fill="#F87171" fillOpacity="0.28" />

    {/* Valles Marineris — Iconic grand equatorial canyon system */}
    <path
      d="M 28 96 Q 64 91, 98 98 T 156 92"
      stroke="#1F0202"
      strokeOpacity="0.85"
      strokeWidth="3.2"
      strokeLinecap="round"
    />
    <path
      d="M 30 94.5 Q 64 89.5, 98 96.5 T 156 90.5"
      stroke="#FCA5A5"
      strokeOpacity="0.48"
      strokeWidth="1.2"
      strokeLinecap="round"
    />
    {/* Canyon tributaries */}
    <path
      d="M 52 95 L 44 88 M 78 96 L 86 104 M 114 96 L 124 89"
      stroke="#2A0404"
      strokeOpacity="0.7"
      strokeWidth="1.5"
      strokeLinecap="round"
    />

    {/* Olympus Mons & Tharsis Montes (Volcanic shields with glowing caldera rings) */}
    <circle cx="34" cy="66" r="8.5" fill="#7F1D1D" fillOpacity="0.7" />
    <circle cx="34" cy="66" r="8.5" stroke="#FCA5A5" strokeOpacity="0.45" strokeWidth="1.1" />
    <circle cx="34" cy="66" r="2.8" fill="#2A0404" fillOpacity="0.85" />

    {/* Three aligned Tharsis volcanoes (Ascraeus, Pavonis, Arsia Mons) */}
    <circle cx="52" cy="74" r="4.5" fill="#7F1D1D" fillOpacity="0.65" stroke="#F87171" strokeOpacity="0.4" strokeWidth="0.9" />
    <circle cx="46" cy="83" r="4.5" fill="#7F1D1D" fillOpacity="0.65" stroke="#F87171" strokeOpacity="0.4" strokeWidth="0.9" />
    <circle cx="40" cy="92" r="4.5" fill="#7F1D1D" fillOpacity="0.65" stroke="#F87171" strokeOpacity="0.4" strokeWidth="0.9" />

    {/* Hellas Planitia & Impact Craters */}
    <ellipse cx="144" cy="130" rx="20" ry="12" fill="#450A0A" fillOpacity="0.65" />
    <ellipse cx="145" cy="131" rx="20" ry="12" stroke="#FCA5A5" strokeOpacity="0.38" strokeWidth="1.2" />

    <ellipse cx="74" cy="128" rx="13" ry="8.5" fill="#3B0404" fillOpacity="0.65" />
    <ellipse cx="75" cy="129" rx="13" ry="8.5" stroke="#F87171" strokeOpacity="0.35" strokeWidth="1" />

    <circle cx="112" cy="68" r="6" fill="#450A0A" fillOpacity="0.6" stroke="#FCA5A5" strokeOpacity="0.35" strokeWidth="1" />
    <circle cx="168" cy="82" r="7.5" fill="#3B0404" fillOpacity="0.6" stroke="#F87171" strokeOpacity="0.35" strokeWidth="1" />
    <circle cx="96" cy="116" r="5" fill="#2A0404" fillOpacity="0.65" />
    <circle cx="22" cy="122" r="6.5" fill="#3B0404" fillOpacity="0.6" />
  </g>
);

const RedPlanetHero: React.FC = () => (
  <div className="relative w-44 h-44 sm:w-48 sm:h-48 flex items-center justify-center select-none">
    {/* Bright pulsing radial light flare that illuminates the surrounding space */}
    <div className="red-planet-flare absolute -inset-10 rounded-full pointer-events-none blur-xl" />

    <div className="red-planet-container relative w-full h-full flex items-center justify-center">
      <svg
        viewBox="0 0 200 200"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-full overflow-visible"
      >
        <defs>
          {/* Base Mars Red/Crimson spherical gradient */}
          <radialGradient id="marsSphereBase" cx="35%" cy="30%" r="70%">
            <stop offset="0%" stopColor="#FCA5A5" />
            <stop offset="18%" stopColor="#EF4444" />
            <stop offset="45%" stopColor="#DC2626" />
            <stop offset="70%" stopColor="#991B1B" />
            <stop offset="88%" stopColor="#450A0A" />
            <stop offset="100%" stopColor="#180202" />
          </radialGradient>

          {/* Procedural rocky Martian surface granulation filter */}
          <filter id="marsRockyNoise" x="0%" y="0%" width="100%" height="100%">
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.065"
              numOctaves="4"
              seed="14"
              result="noise"
            />
            <feColorMatrix
              type="matrix"
              values="
                0.6 0   0   0 0.25
                0   0.1 0   0 0.02
                0   0   0.1 0 0.02
                0   0   0   0.32 0"
              in="noise"
              result="coloredNoise"
            />
            <feBlend mode="multiply" in="SourceGraphic" in2="coloredNoise" />
          </filter>

          {/* 3D Spherical limb darkening around all edges + Day/Night terminator */}
          <radialGradient id="marsTerminator" cx="30%" cy="28%" r="74%">
            <stop offset="0%" stopColor="#000000" stopOpacity="0" />
            <stop offset="52%" stopColor="#1A0202" stopOpacity="0.18" />
            <stop offset="76%" stopColor="#0D0101" stopOpacity="0.68" />
            <stop offset="92%" stopColor="#050000" stopOpacity="0.92" />
            <stop offset="100%" stopColor="#020000" stopOpacity="0.98" />
          </radialGradient>

          {/* Spherical edge vignette so flat scrolling map looks curved at the horizon */}
          <radialGradient id="marsEdgeCurvature" cx="50%" cy="50%" r="50%">
            <stop offset="65%" stopColor="#000000" stopOpacity="0" />
            <stop offset="88%" stopColor="#2A0303" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#050000" stopOpacity="0.82" />
          </radialGradient>

          {/* Atmospheric red/scarlet Fresnel rim glow */}
          <radialGradient id="marsAtmosphereRim" cx="50%" cy="50%" r="50%">
            <stop offset="76%" stopColor="#DC2626" stopOpacity="0" />
            <stop offset="91%" stopColor="#EF4444" stopOpacity="0.42" />
            <stop offset="97%" stopColor="#FCA5A5" stopOpacity="0.82" />
            <stop offset="100%" stopColor="#FF2E2E" stopOpacity="1" />
          </radialGradient>

          {/* Sunlit upper-left atmospheric arc */}
          <linearGradient id="marsSunlitArc" x1="12%" y1="8%" x2="82%" y2="88%">
            <stop offset="0%" stopColor="#FFF1F2" stopOpacity="0.95" />
            <stop offset="38%" stopColor="#F87171" stopOpacity="0.7" />
            <stop offset="75%" stopColor="#DC2626" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#000000" stopOpacity="0" />
          </linearGradient>

          <clipPath id="marsGlobeClip">
            <circle cx="100" cy="100" r="78" />
          </clipPath>
        </defs>

        {/* Outer glowing Martian corona */}
        <circle cx="100" cy="100" r="88" fill="#DC2626" fillOpacity="0.18" />
        <circle cx="100" cy="100" r="82" stroke="#EF4444" strokeOpacity="0.48" strokeWidth="1.75" />

        {/* Clipped 3D Mars Globe */}
        <g clipPath="url(#marsGlobeClip)">
          {/* 1. Core Red Mars sphere */}
          <circle cx="100" cy="100" r="78" fill="url(#marsSphereBase)" />

          {/* 2. Procedural rocky granulation layer */}
          <circle
            cx="100"
            cy="100"
            r="78"
            fill="url(#marsSphereBase)"
            filter="url(#marsRockyNoise)"
          />

          {/* 3. Tilted Martian Axis (-23 deg like real Mars) with Seamless 360° Longitudinal Scroll */}
          <g transform="rotate(-23 100 100)">
            {/* Scrolling Martian Continents, Volcanoes, Valles Marineris & Craters (2 seamless 200px tiles) */}
            <g className="mars-surface-scroll">
              <MarsMapTile offsetX={0} />
              <MarsMapTile offsetX={200} />
            </g>

            {/* Subtle high-altitude red dust storm wisps moving in parallax */}
            <g className="mars-atmosphere-scroll" opacity="0.32">
              <path
                d="M 15 62 Q 55 56, 95 64 T 185 58 M 215 62 Q 255 56, 295 64 T 385 58"
                stroke="#FECACA"
                strokeWidth="4"
                strokeLinecap="round"
              />
              <path
                d="M 40 112 Q 85 106, 135 114 T 195 108 M 240 112 Q 285 106, 335 114 T 395 108"
                stroke="#FCA5A5"
                strokeWidth="3"
                strokeLinecap="round"
              />
            </g>

            {/* North & South Polar Ice/Dust Caps (tinted warm crimson-white) */}
            <ellipse cx="100" cy="23" rx="44" ry="8.5" fill="#FFE4E6" fillOpacity="0.45" />
            <ellipse cx="100" cy="21" rx="28" ry="5" fill="#FFFFFF" fillOpacity="0.5" />
            <ellipse cx="100" cy="177" rx="38" ry="7.5" fill="#FECACA" fillOpacity="0.32" />
          </g>

          {/* 4. 3D Spherical horizon curvature & Day/Night Terminator Shadow */}
          <circle cx="100" cy="100" r="78" fill="url(#marsEdgeCurvature)" />
          <circle cx="100" cy="100" r="78" fill="url(#marsTerminator)" />

          {/* 5. Inner Atmospheric Fresnel Rim */}
          <circle cx="100" cy="100" r="78" fill="url(#marsAtmosphereRim)" />
        </g>

        {/* 6. Crisp sunlit atmospheric rim along upper-left edge */}
        <circle
          cx="100"
          cy="100"
          r="78"
          stroke="url(#marsSunlitArc)"
          strokeWidth="2.5"
        />
      </svg>
    </div>
  </div>
);

export const AssistantScreen: React.FC<AssistantScreenProps> = ({
  sessionId,
  turns,
  onUpdateTurns,
  onNavigateScreen,
}) => {
  const { role, token } = useAuth();
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [openSourcesTurnId, setOpenSourcesTurnId] = useState<string | null>(null);
  const [expandedSourceKey, setExpandedSourceKey] = useState<string | null>(null);
  const [copiedNoteId, setCopiedNoteId] = useState<string | null>(null);

  const chatEndRef = useRef<HTMLDivElement | null>(null);

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

    onUpdateTurns(sessionId, (prev) => [...prev, userTurn]);
    setIsLoading(true);

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
      onUpdateTurns(sessionId, (prev) => [...prev, assistantTurn]);
    } catch (err: any) {
      const errTurn: ChatTurn = {
        id: assistantTurnId,
        role: "assistant",
        content: `Сервер бэкенда (порт 8000) не запущен или недоступен: ${err?.message || ""}`,
        timestamp: new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }),
      };
      onUpdateTurns(sessionId, (prev) => [...prev, errTurn]);
    } finally {
      setIsLoading(false);
    }
  };

  const renderApprovalTimeline = (rec: ApprovalRecommendation) => (
    <div className="mt-4 p-5 rounded-2xl bg-[#111115] border border-white/[0.1] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <GitMerge className="w-4 h-4 text-[#C50337]" />
          <span className="text-sm font-semibold text-white">
            Маршрут визирования (Правило № {rec.rule_number})
          </span>
        </div>
        <span className="text-xs text-zinc-400">
          Подписант: <strong className="text-white">{rec.signatory}</strong>
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-5 gap-2.5">
        {rec.stages.map((st) => (
          <div
            key={`${st.order}-${st.role_name}`}
            className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.07] space-y-1"
          >
            <div className="text-xs font-mono text-zinc-400">Этап {st.order}</div>
            <div className="text-sm font-semibold text-white leading-snug">{st.department}</div>
            <div className="text-xs text-zinc-400">{st.role_name}</div>
          </div>
        ))}
      </div>
    </div>
  );

  const renderGeneratedDocumentCard = (doc: DocumentGenerateResponse) => (
    <div className="mt-4 p-5 rounded-2xl bg-[#111115] border border-white/[0.16] space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <CheckCircle2 className="w-5 h-5 text-[#C50337]" />
          <div>
            <div className="text-sm font-semibold text-white">Проект документа готов</div>
            <div className="text-xs text-zinc-400 font-mono">{doc.file_name}</div>
          </div>
        </div>

        <button
          onClick={() => void downloadGeneratedDocx(doc.file_name, token)}
          className="px-4 py-2 rounded-xl bg-[#C50337] hover:opacity-90 text-white text-sm font-medium flex items-center gap-2 transition"
        >
          <Download className="w-4 h-4" />
          <span>Скачать .DOCX</span>
        </button>
      </div>

      <div className="p-3 rounded-xl bg-black/40 border border-white/[0.08] flex items-center justify-between gap-3">
        <div className="text-xs text-zinc-300 font-mono truncate">{doc.note_text}</div>
        <button
          onClick={() => {
            navigator.clipboard?.writeText(doc.note_text);
            setCopiedNoteId(doc.project_id);
            setTimeout(() => setCopiedNoteId(null), 1800);
          }}
          className="px-3 py-1 rounded-lg bg-white/[0.08] hover:bg-white/[0.14] text-xs text-white shrink-0 flex items-center gap-1.5"
        >
          <Copy className="w-3.5 h-3.5" />
          <span>{copiedNoteId === doc.project_id ? "Скопировано" : "Копировать"}</span>
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex-1 h-screen zyricon-stage-bg flex flex-col justify-between overflow-hidden relative">
      <div className="flex-1 overflow-y-auto px-6 sm:px-12 py-8">
        {turns.length === 0 ? (
          /* HERO STAGE: 3D RED PLANET + TYPEWRITER HEADING WITH FONT CYCLING + INPUT BOX */
          <div className="max-w-4xl mx-auto flex flex-col items-center justify-start pt-2 sm:pt-6 space-y-9">
            <div className="flex flex-col items-center text-center space-y-5">
              <RedPlanetHero />

              <TypewriterHeroHeading />
            </div>

            <div className="w-full space-y-5">
              {/* Large Executive Input Box */}
              <div className="zyricon-input-box rounded-2xl p-6 flex items-end gap-4">
                <textarea
                  rows={2}
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void handleSendQuery();
                    }
                  }}
                  placeholder="Задайте вопрос по регламенту или укажите задачу..."
                  className="flex-1 bg-transparent text-lg text-white placeholder-zinc-500 focus:outline-none resize-none leading-relaxed"
                />

                <button
                  type="button"
                  disabled={!inputText.trim() || isLoading}
                  onClick={() => void handleSendQuery()}
                  className="px-6 py-3 rounded-xl bg-[#C50337] hover:opacity-90 disabled:opacity-35 flex items-center gap-2.5 text-base font-semibold text-white transition shrink-0"
                >
                  <span>Отправить</span>
                  <ArrowUp className="w-5 h-5" />
                </button>
              </div>

              {/* 2x2 Quick Prompts */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                {QUICK_SCENARIOS.map((sc) => (
                  <button
                    key={sc.id}
                    onClick={() => void handleSendQuery(sc.prompt)}
                    className="text-left px-5 py-4 rounded-xl bg-[#111115] hover:bg-white/[0.06] border border-white/[0.1] hover:border-white/[0.24] text-base font-medium text-zinc-200 transition flex items-center justify-between gap-3"
                  >
                    <span>{sc.title}</span>
                    <span className="text-zinc-500 text-lg">→</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          /* ACTIVE CONVERSATION */
          <div className="max-w-4xl mx-auto space-y-6 pb-8 pt-2">
            {turns.map((turn) => {
              if (turn.role === "user") {
                return (
                  <div key={turn.id} className="flex justify-end">
                    <div className="max-w-2xl rounded-2xl rounded-tr-sm px-5 py-4 bg-[#C50337] text-white text-base">
                      <div className="whitespace-pre-wrap leading-relaxed">{turn.content}</div>
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
              const sourcesOpen = openSourcesTurnId === turn.id;

              return (
                <div
                  key={turn.id}
                  className="zyricon-glass-card rounded-2xl p-6 space-y-4 border border-white/[0.1]"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <div className="w-6 h-6 rounded-full zyricon-orb" />
                      <span className="text-sm font-semibold text-white">DoCorp</span>
                    </div>

                    {zeroHallucination ? (
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#C50337]/20 border border-[#C50337]/50 text-xs text-white">
                        <ShieldAlert className="w-3.5 h-3.5 text-[#C50337]" />
                        Вопрос вне регламентов ДОУ
                      </span>
                    ) : (
                      typeof meta?.relevance_score === "number" && (
                        <span className="text-xs font-mono text-zinc-400">
                          Релевантность: {meta.relevance_score.toFixed(0)}%
                        </span>
                      )
                    )}
                  </div>

                  <div className="text-base text-zinc-100 leading-relaxed whitespace-pre-wrap">
                    {turn.content}
                  </div>

                  {needsClarif && (
                    <div className="p-4 rounded-xl bg-[#141419] border border-[#C50337]/50 space-y-3">
                      <div className="flex items-start gap-2.5">
                        <HelpCircle className="w-5 h-5 text-[#C50337] shrink-0 mt-0.5" />
                        <div className="text-sm font-medium text-white">
                          {clarifQ || "Выберите уточняющий вариант:"}
                        </div>
                      </div>

                      {quickReplies.length > 0 && (
                        <div className="flex flex-wrap gap-2">
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

                  {generatedDoc && renderGeneratedDocumentCard(generatedDoc)}

                  {approvalRec && renderApprovalTimeline(approvalRec)}

                  {(sources.length > 0 || terms.length > 0) && (
                    <div className="pt-2 border-t border-white/[0.08]">
                      <button
                        onClick={() =>
                          setOpenSourcesTurnId(sourcesOpen ? null : turn.id)
                        }
                        className="inline-flex items-center gap-2 text-xs font-medium text-zinc-300 hover:text-white transition"
                      >
                        <FileText className="w-4 h-4 text-[#C50337]" />
                        <span>
                          {sourcesOpen
                            ? "Скрыть источники"
                            : `Источники ОД-184 (${sources.length})`}
                        </span>
                        {sourcesOpen ? (
                          <ChevronUp className="w-4 h-4" />
                        ) : (
                          <ChevronDown className="w-4 h-4" />
                        )}
                      </button>

                      {sourcesOpen && (
                        <div className="mt-3 space-y-3">
                          {terms.length > 0 && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              {terms.map((term, i) => (
                                <div
                                  key={`${term.canonical}-${i}`}
                                  className="p-3 rounded-xl bg-white/[0.03] border border-white/[0.07] text-xs"
                                >
                                  <span className="font-semibold text-white">{term.canonical}</span> —{" "}
                                  <span className="text-zinc-300">{term.expansion}</span>
                                </div>
                              ))}
                            </div>
                          )}

                          {sources.map((src, idx) => {
                            const srcKey = `${turn.id}-src-${idx}`;
                            const isExpanded = expandedSourceKey === srcKey;
                            return (
                              <div
                                key={srcKey}
                                className="p-3.5 rounded-xl bg-[#111115] border border-white/[0.08] space-y-2"
                              >
                                <div className="flex items-center justify-between text-xs">
                                  <span className="font-semibold text-white">
                                    {src.document_code} • Пункт {src.clause || "—"}
                                  </span>
                                  <div className="flex items-center gap-2">
                                    <span className="font-mono text-zinc-400">
                                      {src.relevance_pct.toFixed(0)}%
                                    </span>
                                    {src.full_content && (
                                      <button
                                        onClick={() =>
                                          setExpandedSourceKey(isExpanded ? null : srcKey)
                                        }
                                        className="px-2 py-0.5 rounded bg-white/[0.07] text-white"
                                      >
                                        {isExpanded ? "Свернуть" : "Полный текст"}
                                      </button>
                                    )}
                                  </div>
                                </div>
                                <p className="text-xs text-zinc-300 border-l-2 border-[#C50337] pl-2.5">
                                  «{src.quote}»
                                </p>
                                {isExpanded && src.full_content && (
                                  <div className="p-3 rounded-lg bg-black/50 text-xs text-zinc-200 whitespace-pre-wrap">
                                    {src.full_content}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}

            {isLoading && (
              <div className="zyricon-glass-card rounded-2xl p-5 flex items-center gap-3 text-sm text-zinc-300">
                <div className="w-5 h-5 rounded-full zyricon-orb animate-spin shrink-0" />
                <span>Анализ положений Инструкции № ОД-184...</span>
              </div>
            )}

            <div ref={chatEndRef} />
          </div>
        )}
      </div>

      {/* Bottom Sticky Input Bar when conversation is active */}
      {turns.length > 0 && (
        <div className="px-6 sm:px-12 py-4 bg-[#08080A] border-t border-white/[0.08]">
          <div className="max-w-4xl mx-auto">
            <div className="zyricon-input-box rounded-2xl p-3.5 flex items-center gap-3">
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
                placeholder="Задайте вопрос или уточните параметр..."
                className="flex-1 bg-transparent text-base text-white placeholder-zinc-500 focus:outline-none px-2"
              />
              <button
                disabled={!inputText.trim() || isLoading}
                onClick={() => void handleSendQuery()}
                className="px-5 py-2.5 rounded-xl bg-[#C50337] hover:opacity-90 disabled:opacity-35 flex items-center gap-2 text-sm font-semibold text-white transition shrink-0"
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

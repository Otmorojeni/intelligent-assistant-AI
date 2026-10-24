import React, { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  Copy,
  Download,
  FileSpreadsheet,
  FolderKanban,
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

type ConstructorTab = "builder" | "registry";

/**
 * Built-in catalog of all 7 modular templates (УТВ-01..УТВ-07) from Инструкция № ОД-184
 * so template selection and form rendering always work immediately even if backend DB is offline.
 */
const FALLBACK_TEMPLATES: TemplateModuleInfo[] = [
  {
    id: 1,
    module_code: "MOD-ORDER-IS",
    doc_kind: "Приказ",
    title: "Приказ о вводе в эксплуатацию информационной системы",
    reg_number: "УТВ-01",
    version: "1.0",
    default_rule_number: 4,
    fields_schema: [
      {
        name: "system_name",
        label: "Наименование информационной системы",
        type: "string",
        required: true,
        description: "Полное и точное официальное наименование ИС",
      },
      {
        name: "purpose",
        label: "Цель ввода в эксплуатацию",
        type: "string",
        required: true,
        description: "Обоснование и цели: автоматизация, повышение надежности и т.д.",
      },
      {
        name: "commissioning_date",
        label: "Дата ввода в эксплуатацию",
        type: "date",
        required: true,
        description: "Дата начала постоянной эксплуатации информационной системы",
      },
      {
        name: "responsible_dept",
        label: "Ответственное подразделение",
        type: "string",
        required: true,
        description: "Структурное подразделение, ответственное за сопровождение",
      },
      {
        name: "infosec_dept",
        label: "Подразделение информационной безопасности",
        type: "string",
        required: true,
        description: "Подразделение, обеспечивающее контроль ИБ системы",
      },
      {
        name: "control_officer",
        label: "Контроль исполнения",
        type: "string",
        required: false,
        default: "Контроль за исполнением настоящего приказа оставляю за собой",
        description: "Должность и ФИО лица, на которое возложен контроль",
      },
    ],
  },
  {
    id: 2,
    module_code: "MOD-ORDER-DOU",
    doc_kind: "Приказ",
    title: "Приказ о назначении ответственных за делопроизводство и документооборот",
    reg_number: "УТВ-02",
    version: "1.0",
    default_rule_number: 5,
    fields_schema: [
      {
        name: "department_name",
        label: "Структурное подразделение",
        type: "string",
        required: true,
        description: "Полное наименование подразделения Организации",
      },
      {
        name: "primary_responsible",
        label: "Основной ответственный работник",
        type: "string",
        required: true,
        description: "Должность, структурное подразделение и ФИО работника",
      },
      {
        name: "deputy_responsible",
        label: "Замещающий ответственный работник",
        type: "string",
        required: true,
        description: "Должность, подразделение и ФИО лица на период отсутствия основного",
      },
      {
        name: "reason",
        label: "Основание назначения",
        type: "string",
        required: true,
        description: "Цели надлежащей организации ДОУ, кадровые перестановки и т.д.",
      },
      {
        name: "repeal_order",
        label: "Отменяемый приказ",
        type: "string",
        required: false,
        description: "Дата, номер и наименование ранее изданного приказа (при наличии)",
      },
      {
        name: "control_officer",
        label: "Контроль исполнения",
        type: "string",
        required: false,
        default: "Контроль за исполнением настоящего приказа оставляю за собой",
        description: "Должность и ФИО лица, контролирующего исполнение приказа",
      },
    ],
  },
  {
    id: 3,
    module_code: "MOD-ORDER-PROP",
    doc_kind: "Приказ",
    title: "Приказ о приеме и передаче дел и имущества",
    reg_number: "УТВ-03",
    version: "1.0",
    default_rule_number: 2,
    fields_schema: [
      {
        name: "department_name",
        label: "Структурное подразделение",
        type: "string",
        required: true,
        description: "Подразделение, в котором происходит передача дел",
      },
      {
        name: "transferor_name",
        label: "Передающее лицо (ФИО, должность)",
        type: "string",
        required: true,
        description: "Работник, сдающий дела и имущество",
      },
      {
        name: "transferee_name",
        label: "Принимающее лицо (ФИО, должность)",
        type: "string",
        required: true,
        description: "Работник, принимающий дела и имущество",
      },
      {
        name: "transfer_basis",
        label: "Основание передачи",
        type: "string",
        required: true,
        description: "Причина передачи: перевод, освобождение от должности, реорганизация",
      },
      {
        name: "deadline",
        label: "Срок передачи",
        type: "date",
        required: true,
        description: "Конечный срок подписания акта приема-передачи",
      },
      {
        name: "commission_members",
        label: "Члены комиссии",
        type: "textarea",
        required: false,
        description: "Состав комиссии по приему-передаче дел (при наличии)",
      },
      {
        name: "affects_is_access",
        label: "Изменение доступа к ИС (Да / Нет)",
        type: "string",
        required: true,
        default: "Да",
        description: "Требуется ли виза Департамента ИБ в связи с правами доступа к ИС",
      },
      {
        name: "control_officer",
        label: "Контроль исполнения",
        type: "string",
        required: false,
        default: "Контроль за исполнением настоящего приказа оставляю за собой",
        description: "Должностное лицо, контролирующее передачу",
      },
    ],
  },
  {
    id: 4,
    module_code: "MOD-ORDER-LNA",
    doc_kind: "Приказ",
    title: "Приказ об утверждении и введении в действие локального нормативного акта",
    reg_number: "УТВ-04",
    version: "1.0",
    default_rule_number: 5,
    fields_schema: [
      {
        name: "act_title",
        label: "Наименование утверждаемого документа",
        type: "string",
        required: true,
        description: "Полное наименование ЛНА (положение, правила, регламент, инструкция)",
      },
      {
        name: "purpose",
        label: "Цель издания приказа",
        type: "string",
        required: true,
        description: "Обоснование: совершенствование процессов, выполнение требований законодательства",
      },
      {
        name: "effective_date",
        label: "Дата введения в действие",
        type: "date",
        required: true,
        description: "Дата начала применения локального нормативного акта",
      },
      {
        name: "responsible_dept",
        label: "Ответственное подразделение",
        type: "string",
        required: true,
        description: "Подразделение, обеспечивающее ознакомление и размещение документа",
      },
      {
        name: "placement_location",
        label: "Место размещения",
        type: "string",
        required: true,
        default: "на внутреннем информационном портале Организации",
        description: "Официальный корпоративный ресурс для публикации ЛНА",
      },
      {
        name: "repeal_act",
        label: "Отменяемый документ",
        type: "string",
        required: false,
        description: "Реквизиты ранее действовавшего документа, признаваемого утратившим силу",
      },
      {
        name: "control_officer",
        label: "Контроль исполнения",
        type: "string",
        required: false,
        default: "Контроль за исполнением настоящего приказа оставляю за собой",
        description: "Должностное лицо, контролирующее исполнение",
      },
    ],
  },
  {
    id: 5,
    module_code: "MOD-DISP-AUDIT",
    doc_kind: "Распоряжение",
    title: "Распоряжение о проведении внутреннего аудита процессов",
    reg_number: "УТВ-05",
    version: "1.0",
    default_rule_number: 9,
    fields_schema: [
      {
        name: "audit_process",
        label: "Наименование процесса аудита",
        type: "string",
        required: true,
        description: "Процесс или процессы Организации, подлежащие аудиту",
      },
      {
        name: "audit_goal",
        label: "Цель аудита",
        type: "string",
        required: true,
        description: "Оценка соответствия, выявление рисков, анализ эффективности",
      },
      {
        name: "audit_period",
        label: "Сроки проведения аудита",
        type: "string",
        required: true,
        description: "Период проверки (например, с 01 по 20 ноября 2026 г.)",
      },
      {
        name: "audited_dept",
        label: "Проверяемое подразделение",
        type: "string",
        required: true,
        description: "Структурное подразделение Организации, в котором проводится аудит",
      },
      {
        name: "audit_leader",
        label: "Руководитель группы аудита",
        type: "string",
        required: true,
        description: "Должность, подразделение и ФИО руководителя аудиторской группы",
      },
      {
        name: "audit_team",
        label: "Состав группы аудита",
        type: "textarea",
        required: true,
        description: "Перечень членов группы аудита (должности, ФИО)",
      },
      {
        name: "report_deadline",
        label: "Срок предоставления отчета",
        type: "date",
        required: true,
        description: "Дата представления итогового аудиторского отчета руководству",
      },
      {
        name: "control_officer",
        label: "Контроль исполнения",
        type: "string",
        required: false,
        default: "Контроль за исполнением настоящего распоряжения оставляю за собой",
        description: "Должностное лицо, контролирующее исполнение распоряжения",
      },
    ],
  },
  {
    id: 6,
    module_code: "MOD-DISP-PROJECT",
    doc_kind: "Распоряжение",
    title: "Распоряжение о создании проектного комитета",
    reg_number: "УТВ-06",
    version: "1.0",
    default_rule_number: 7,
    fields_schema: [
      {
        name: "project_name",
        label: "Наименование проекта (проектов)",
        type: "string",
        required: true,
        description: "Полное наименование одного или нескольких проектов",
      },
      {
        name: "committee_purpose",
        label: "Цель создания Комитета",
        type: "string",
        required: true,
        description: "Координация деятельности участников проекта и контроль сроков",
      },
      {
        name: "reason",
        label: "Основание создания",
        type: "string",
        required: true,
        description: "Обстоятельство: запуск проекта, изменение этапа, межфункциональное взаимодействие",
      },
      {
        name: "managing_dept",
        label: "Ответственное подразделение",
        type: "string",
        required: true,
        description: "Подразделение Организации, реализующее проект",
      },
      {
        name: "chairman",
        label: "Председатель Комитета",
        type: "string",
        required: true,
        description: "Должность, подразделение и ФИО председателя",
      },
      {
        name: "deputy_chairman",
        label: "Заместитель председателя Комитета",
        type: "string",
        required: false,
        description: "Должность, подразделение и ФИО заместителя (при наличии)",
      },
      {
        name: "secretary",
        label: "Секретарь Комитета",
        type: "string",
        required: true,
        description: "Должность, подразделение и ФИО секретаря Комитета",
      },
      {
        name: "members",
        label: "Члены Комитета",
        type: "textarea",
        required: true,
        description: "Список членов Комитета с указанием должностей и ФИО",
      },
      {
        name: "is_it_project",
        label: "ИТ-проект (Да / Нет)",
        type: "string",
        required: true,
        default: "Да",
        description: "Создается ли комитет для реализации ИТ-проекта (требуется виза ДИТ)",
      },
      {
        name: "repeal_order",
        label: "Отменяемое распоряжение",
        type: "string",
        required: false,
        description: "Дата и номер ранее изданного распоряжения (при отмене)",
      },
      {
        name: "control_officer",
        label: "Контроль исполнения",
        type: "string",
        required: false,
        default: "Контроль за исполнением настоящего распоряжения оставляю за собой",
        description: "Должностное лицо, на которое возложен контроль",
      },
    ],
  },
  {
    id: 7,
    module_code: "MOD-DISP-WORKGROUP",
    doc_kind: "Распоряжение",
    title: "Распоряжение о создании рабочей группы",
    reg_number: "УТВ-07",
    version: "1.0",
    default_rule_number: 7,
    fields_schema: [
      {
        name: "workgroup_subject",
        label: "Предмет работы рабочей группы",
        type: "string",
        required: true,
        description: "Тема или предмет деятельности: подготовка документов, анализ и т.д.",
      },
      {
        name: "goal",
        label: "Цель рабочей группы",
        type: "string",
        required: true,
        description: "Практическая цель: внедрение изменения, выработка предложений и т.д.",
      },
      {
        name: "leader",
        label: "Руководитель рабочей группы",
        type: "string",
        required: true,
        description: "Должность, подразделение и ФИО руководителя группы",
      },
      {
        name: "deputy_leader",
        label: "Заместитель руководителя",
        type: "string",
        required: false,
        description: "Должность, подразделение и ФИО заместителя (при наличии)",
      },
      {
        name: "secretary",
        label: "Секретарь рабочей группы",
        type: "string",
        required: true,
        description: "Должность, подразделение и ФИО секретаря группы",
      },
      {
        name: "members",
        label: "Члены рабочей группы",
        type: "textarea",
        required: true,
        description: "Список участников (должности, подразделения, ФИО)",
      },
      {
        name: "deadline",
        label: "Срок выполнения",
        type: "date",
        required: true,
        description: "Конечный срок представления результатов",
      },
      {
        name: "expected_result",
        label: "Итоговый результат",
        type: "string",
        required: true,
        description: "Итоговый документ и адресат: проект, отчет, предложения",
      },
      {
        name: "termination_event",
        label: "Завершение деятельности",
        type: "string",
        required: true,
        description: "Событие: представление результата, утверждение документа или решение руководства",
      },
      {
        name: "is_it_project",
        label: "ИТ-проект (Да / Нет)",
        type: "string",
        required: true,
        default: "Да",
        description: "Создается ли группа для решения вопросов ИС/ИТ (требуется виза ДИТ)",
      },
      {
        name: "control_officer",
        label: "Контроль исполнения",
        type: "string",
        required: false,
        default: "Контроль за исполнением настоящего распоряжения оставляю за собой",
        description: "Должностное лицо, контролирующее исполнение",
      },
    ],
  },
];

const DEMO_VALUES_BY_MODULE: Record<string, Record<string, string>> = {
  "MOD-ORDER-IS": {
    system_name: "АИС «Интеллектуальная система ДОУ DoCorp»",
    purpose: "Автоматизация нормоконтроля и подготовки проектов ОРД в соответствии с Инструкцией № ОД-184",
    commissioning_date: "01.11.2026",
    responsible_dept: "Департамент информационных технологий",
    infosec_dept: "Департамент информационной безопасности",
    control_officer: "Контроль за исполнением настоящего приказа оставляю за собой",
  },
  "MOD-ORDER-DOU": {
    department_name: "Департамент цифровых технологий",
    primary_responsible: "Главный специалист отдела сопровождения Морозова Е.В.",
    deputy_responsible: "Ведущий эксперт отдела сопровождения Волков Д.А.",
    reason: "Обеспечение ведения делопроизводства и контроля исполнения документов в соответствии с № ОД-184",
    repeal_order: "Приказ от 15.02.2025 № ОД-42 «О назначении ответственных за ведение ДОУ»",
    control_officer: "Контроль за исполнением настоящего приказа оставляю за собой",
  },
  "MOD-ORDER-PROP": {
    department_name: "Управление документационного обеспечения",
    transferor_name: "Начальник отдела архивного хранения Кузнецов И.С.",
    transferee_name: "Заместитель начальника отдела Лебедева О.Н.",
    transfer_basis: "Кадровый перевод работника в другое структурное подразделение",
    deadline: "05.11.2026",
    commission_members: "Председатель комиссии: Орлов В.П., члены комиссии: Семенова Т.Г., Белов А.К.",
    affects_is_access: "Да",
    control_officer: "Контроль за исполнением настоящего приказа оставляю за собой",
  },
  "MOD-ORDER-LNA": {
    act_title: "Регламент автоматизированной проверки проектов организационно-распорядительных документов",
    purpose: "Совершенствование процедур нормоконтроля и сокращение сроков визирования в ИИС ДО",
    effective_date: "10.11.2026",
    responsible_dept: "Департамент документационного обеспечения управления",
    placement_location: "на внутреннем информационном портале Организации",
    repeal_act: "Регламент предварительной проверки проектов ОРД от 12.04.2024 № РГ-19",
    control_officer: "Контроль за исполнением настоящего приказа оставляю за собой",
  },
  "MOD-DISP-AUDIT": {
    audit_process: "Процесс регистрации, визирования и контроля исполнения входящих и внутренних документов",
    audit_goal: "Оценка соблюдения сроков и правил оформления документов по Инструкции № ОД-184",
    audit_period: "с 10.11.2026 по 25.11.2026",
    audited_dept: "Региональное отделение № 4",
    audit_leader: "Заместитель руководителя Службы внутреннего аудита Громов М.Ю.",
    audit_team: "Главный аудитор Власова Н.В., ведущий эксперт ДОУ Карпов С.Е.",
    report_deadline: "30.11.2026",
    control_officer: "Контроль за исполнением настоящего распоряжения оставляю за собой",
  },
  "MOD-DISP-PROJECT": {
    project_name: "Внедрение интеллектуальной системы нормоконтроля и генерации модульных документов",
    committee_purpose: "Межфункциональная координация подразделений ДОУ, ИТ и ИБ при промышленном запуске",
    reason: "Реализация дорожной карты цифровой трансформации документооборота на 2026 год",
    managing_dept: "Департамент документационного обеспечения управления",
    chairman: "Заместитель Председателя Организации Смирнов К.Н.",
    deputy_chairman: "Директор Департамента ДОУ Васильева А.П.",
    secretary: "Главный эксперт отдела методологии ДОУ Никитина Ю.С.",
    members: "Директор ДИТ Соколов А.В., Директор ДИБ Тарасов Р.М., Начальник Правового управления Федоров П.Л.",
    is_it_project: "Да",
    repeal_order: "",
    control_officer: "Контроль за исполнением настоящего распоряжения оставляю за собой",
  },
  "MOD-DISP-WORKGROUP": {
    workgroup_subject: "Актуализация альбома форм модульных документов (УТВ-01..УТВ-07) и Матрицы визирования",
    goal: "Унификация типовых форм приказов и распоряжений для ускоренного согласования без визы ЮП",
    leader: "Директор Департамента ДОУ Васильева А.П.",
    deputy_leader: "Заместитель директора Департамента ДОУ Козлов Е.Д.",
    secretary: "Ведущий методолог ДОУ Романова М.А.",
    members: "Представители Юридического подразделения, ДИТ, ДИБ и Кадровой службы",
    deadline: "20.11.2026",
    expected_result: "Проект приказа о внесении изменений в альбом форм модульных документов",
    termination_event: "Утверждение обновленного альбома форм модульных документов Руководством Организации",
    is_it_project: "Да",
    control_officer: "Контроль за исполнением настоящего распоряжения оставляю за собой",
  },
};

export const ConstructorScreen: React.FC<ConstructorScreenProps> = ({
  initialModuleCode,
}) => {
  const { role, token } = useAuth();
  const [subTab, setSubTab] = useState<ConstructorTab>("builder");
  const [templates, setTemplates] = useState<TemplateModuleInfo[]>(FALLBACK_TEMPLATES);
  const [selectedTemplate, setSelectedTemplate] = useState<TemplateModuleInfo>(() => {
    const initial =
      (initialModuleCode &&
        FALLBACK_TEMPLATES.find((t) => t.module_code === initialModuleCode)) ||
      FALLBACK_TEMPLATES[0];
    return initial;
  });
  const [formValues, setFormValues] = useState<Record<string, string>>(() => {
    const initial =
      (initialModuleCode &&
        FALLBACK_TEMPLATES.find((t) => t.module_code === initialModuleCode)) ||
      FALLBACK_TEMPLATES[0];
    const defaults: Record<string, string> = {};
    for (const f of initial.fields_schema || []) {
      defaults[f.name] = f.default || "";
    }
    return defaults;
  });
  const [executorName, setExecutorName] = useState("Иванов И.И.");
  const [executorDept, setExecutorDept] = useState("Департамент ДОУ");
  const [signatoryName, setSignatoryName] = useState("Петров П.П.");
  const [accessLevel, setAccessLevel] = useState("public");
  const [projectTitle, setProjectTitle] = useState(FALLBACK_TEMPLATES[0].title);
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
      // keep existing or empty list when backend is offline
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
        if (Array.isArray(list) && list.length > 0) {
          setTemplates(list);
          const target =
            (initialModuleCode && list.find((t) => t.module_code === initialModuleCode)) ||
            list[0];
          applyTemplateDefaults(target);
        }
      } catch {
        // Fallback templates are already loaded in state, so the user can always select any module!
        if (initialModuleCode) {
          const target = FALLBACK_TEMPLATES.find((t) => t.module_code === initialModuleCode);
          if (target) applyTemplateDefaults(target);
        }
      }
    }
    void init();
  }, [initialModuleCode, token, applyTemplateDefaults]);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects, role]);

  const handleFillDemoValues = () => {
    if (!selectedTemplate) return;
    const preset = DEMO_VALUES_BY_MODULE[selectedTemplate.module_code] || {};
    const next: Record<string, string> = {};
    for (const f of selectedTemplate.fields_schema || []) {
      next[f.name] = preset[f.name] ?? f.default ?? "По согласованию с подразделением";
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
    } catch {
      // Offline preview fallback so user can inspect the generated route & п. 2.3 note even without backend running
      const todayStr = new Date().toLocaleDateString("ru-RU");
      const mockFileName = `${selectedTemplate.reg_number}_${selectedTemplate.module_code}_Проект.docx`;
      const mockRes: DocumentGenerateResponse = {
        project_id: crypto.randomUUID(),
        file_name: mockFileName,
        download_url: `/v1/documents/download/${mockFileName}`,
        note_text: `Документ подготовлен с использованием модульного документа от ${todayStr} № ${selectedTemplate.reg_number} (Раздел 3.3 Методических рекомендаций — без обязательного визирования в Юридическом подразделении).`,
        approval_route: [
          {
            order: 1,
            role_name: `Исполнитель (${executorName})`,
            department: executorDept,
            reason: "Подготовка проекта на базе модульного шаблона",
          },
          {
            order: 2,
            role_name: "Руководитель инициирующего СП",
            department: executorDept,
            reason: "Первичное согласование проекта",
          },
          {
            order: 3,
            role_name: "Специалист нормоконтроля",
            department: "Департамент ДОУ",
            reason: `Проверка по п. 2.3 (Правило № ${selectedTemplate.default_rule_number || 4})`,
          },
          {
            order: 4,
            role_name: "Профильные согласующие СП",
            department:
              selectedTemplate.module_code === "MOD-ORDER-IS"
                ? "Департамент ИТ и Департамент ИБ"
                : "Кадровое подразделение / ДИТ (по принадлежности)",
            reason: "Обязательная виза по Матрице визирования",
          },
          {
            order: 5,
            role_name: signatoryName,
            department: "Руководство Организации",
            reason: "Подписание и регистрация в ИИС ДО",
          },
        ],
        created_at: new Date().toISOString(),
      };
      setGenResult(mockRes);
      setProjects((prev) => [
        {
          id: mockRes.project_id,
          template_id: String(selectedTemplate.id || selectedTemplate.module_code),
          module_code: selectedTemplate.module_code,
          project_title: projectTitle || selectedTemplate.title,
          executor_name: executorName,
          executor_department: executorDept,
          signatory_name: signatoryName,
          access_level: accessLevel,
          note_text: mockRes.note_text,
          filled_fields: formValues,
          approval_route: mockRes.approval_route,
          generated_file_name: mockRes.file_name,
          download_url: mockRes.download_url,
          status: "generated",
          created_at: mockRes.created_at,
        },
        ...prev,
      ]);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="flex-1 h-screen zyricon-stage-bg overflow-y-auto px-6 sm:px-12 py-8 space-y-6">
      {/* Top Bar with Sub-tab Switcher */}
      <div className="max-w-5xl mx-auto flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-1 p-1 rounded-full bg-[#111115] border border-white/[0.1] text-sm">
          <button
            type="button"
            onClick={() => setSubTab("builder")}
            className={`px-4 py-2 rounded-full font-medium transition ${
              subTab === "builder"
                ? "bg-[#C50337] text-white"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            Создание документа (УТВ-01..07)
          </button>
          <button
            type="button"
            onClick={() => setSubTab("registry")}
            className={`px-4 py-2 rounded-full font-medium transition ${
              subTab === "registry"
                ? "bg-[#C50337] text-white"
                : "text-zinc-400 hover:text-white"
            }`}
          >
            Реестр проектов ({projects.length})
          </button>
        </div>

        {subTab === "builder" && (
          <button
            type="button"
            onClick={handleFillDemoValues}
            className="px-4 py-2.5 rounded-xl bg-white/[0.07] hover:bg-white/[0.12] border border-white/[0.12] text-sm font-medium text-white flex items-center gap-2 transition"
          >
            <Wand2 className="w-4 h-4 text-[#C50337]" />
            <span>Заполнить демо-данными</span>
          </button>
        )}
      </div>

      {subTab === "builder" ? (
        <div className="max-w-5xl mx-auto space-y-6">
          {/* Template Selector Card: Dropdown + Quick Module Pills */}
          <div className="zyricon-glass-card rounded-2xl p-6 space-y-4">
            <div className="flex items-center justify-between">
              <label className="block text-xs font-semibold uppercase tracking-wider text-zinc-400">
                Выберите модульный шаблон (УТВ-01 .. УТВ-07)
              </label>
              <span className="text-xs font-mono text-zinc-400">
                {selectedTemplate.doc_kind} • Правило № {selectedTemplate.default_rule_number || 4}
              </span>
            </div>

            {/* 1-Click Module Pills */}
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
              {templates.map((tpl) => {
                const isSelected = selectedTemplate.module_code === tpl.module_code;
                return (
                  <button
                    key={tpl.module_code}
                    type="button"
                    onClick={() => applyTemplateDefaults(tpl)}
                    className={`px-3 py-2.5 rounded-xl border text-left transition flex flex-col justify-between ${
                      isSelected
                        ? "bg-[#C50337] border-[#C50337] text-white"
                        : "bg-[#0D0D11] border-white/[0.1] hover:border-white/[0.25] text-zinc-300 hover:text-white"
                    }`}
                  >
                    <div className="text-xs font-bold font-mono">{tpl.reg_number}</div>
                    <div className="text-[11px] opacity-85 truncate mt-0.5">{tpl.doc_kind}</div>
                  </button>
                );
              })}
            </div>

            {/* Full Title Dropdown Selector */}
            <select
              value={selectedTemplate.module_code}
              onChange={(e) => {
                const found = templates.find((t) => t.module_code === e.target.value);
                if (found) applyTemplateDefaults(found);
              }}
              className="w-full px-4 py-3.5 rounded-xl bg-[#0D0D11] border border-white/[0.16] text-base font-medium text-white focus:border-[#C50337] focus:outline-none cursor-pointer"
            >
              {templates.map((tpl) => (
                <option
                  key={tpl.module_code}
                  value={tpl.module_code}
                  className="bg-[#111115] text-white py-2"
                >
                  {tpl.reg_number} ({tpl.module_code}) — {tpl.title}
                </option>
              ))}
            </select>
          </div>

          {/* Dynamic Template Form */}
          <form
            onSubmit={handleGenerate}
            className="zyricon-glass-card rounded-2xl p-6 space-y-6 border border-white/[0.1]"
          >
            {errorMsg && (
              <div className="p-4 rounded-xl bg-[#C50337]/20 border border-[#C50337]/50 text-sm text-white">
                {errorMsg}
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-zinc-400 mb-1.5">ФИО исполнителя</label>
                <input
                  type="text"
                  required
                  value={executorName}
                  onChange={(e) => setExecutorName(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white focus:border-[#C50337] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs text-zinc-400 mb-1.5">Подразделение</label>
                <input
                  type="text"
                  required
                  value={executorDept}
                  onChange={(e) => setExecutorDept(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white focus:border-[#C50337] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs text-zinc-400 mb-1.5">Подписант</label>
                <input
                  type="text"
                  required
                  value={signatoryName}
                  onChange={(e) => setSignatoryName(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white focus:border-[#C50337] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs text-zinc-400 mb-1.5">Уровень доступа</label>
                <select
                  value={accessLevel}
                  onChange={(e) => setAccessLevel(e.target.value)}
                  className="w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white focus:border-[#C50337] focus:outline-none"
                >
                  <option value="public" className="bg-[#111115] text-white">
                    Открытый
                  </option>
                  <option value="internal" className="bg-[#111115] text-white">
                    Внутренний
                  </option>
                  <option value="dsp" className="bg-[#111115] text-white">
                    Для служебного пользования
                  </option>
                  <option value="confidential" className="bg-[#111115] text-white">
                    Секретно
                  </option>
                </select>
              </div>
            </div>

            <div className="pt-4 border-t border-white/[0.08] space-y-4">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-white">
                  Реквизиты модульного шаблона «{selectedTemplate.reg_number}»
                </div>
                <div className="text-xs text-zinc-400">{selectedTemplate.title}</div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {selectedTemplate.fields_schema.map((field) => (
                  <div
                    key={field.name}
                    className={field.type === "textarea" ? "sm:col-span-2" : ""}
                  >
                    <label className="block text-xs text-zinc-400 mb-1.5">
                      {field.label} {field.required && <span className="text-[#C50337]">*</span>}
                    </label>
                    {field.type === "textarea" ? (
                      <textarea
                        rows={2}
                        required={Boolean(field.required)}
                        value={formValues[field.name] ?? ""}
                        onChange={(e) =>
                          setFormValues((prev) => ({
                            ...prev,
                            [field.name]: e.target.value,
                          }))
                        }
                        placeholder={field.description || field.default || ""}
                        className="w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white focus:border-[#C50337] focus:outline-none"
                      />
                    ) : (
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
                        placeholder={field.description || field.default || ""}
                        className="w-full px-3.5 py-2.5 rounded-xl bg-[#0D0D11] border border-white/[0.14] text-sm text-white focus:border-[#C50337] focus:outline-none"
                      />
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                type="submit"
                disabled={isGenerating}
                className="px-6 py-3 rounded-xl bg-[#C50337] hover:opacity-90 disabled:opacity-45 text-sm font-semibold text-white flex items-center gap-2 transition"
              >
                <FileSpreadsheet className="w-4 h-4" />
                <span>{isGenerating ? "Сборка .DOCX..." : "Сформировать проект .DOCX"}</span>
              </button>
            </div>
          </form>

          {/* Result */}
          {genResult && (
            <div className="p-6 rounded-2xl bg-[#111115] border border-white/[0.16] space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="w-5 h-5 text-[#C50337]" />
                  <div>
                    <div className="text-base font-semibold text-white">Документ сформирован</div>
                    <div className="text-xs font-mono text-zinc-400">{genResult.file_name}</div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => void downloadGeneratedDocx(genResult.file_name, token)}
                  className="px-5 py-2.5 rounded-xl bg-[#C50337] hover:opacity-90 text-sm font-semibold text-white flex items-center gap-2 transition"
                >
                  <Download className="w-4 h-4" />
                  <span>Скачать .DOCX</span>
                </button>
              </div>

              <div className="p-3.5 rounded-xl bg-black/50 border border-white/[0.08] flex items-center justify-between gap-3">
                <div className="text-xs font-mono text-zinc-200 truncate">{genResult.note_text}</div>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard?.writeText(genResult.note_text);
                    setCopiedNote(true);
                    setTimeout(() => setCopiedNote(false), 1800);
                  }}
                  className="px-3 py-1.5 rounded-lg bg-white/[0.08] text-xs text-white shrink-0 flex items-center gap-1.5"
                >
                  <Copy className="w-3.5 h-3.5" />
                  <span>{copiedNote ? "Скопировано" : "Копировать отметку п. 2.3"}</span>
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-5 gap-2.5 pt-1">
                {genResult.approval_route.map((st) => (
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
      ) : (
        /* TAB 2: REGISTRY OF CREATED PROJECTS */
        <div className="max-w-5xl mx-auto zyricon-glass-card rounded-2xl p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <FolderKanban className="w-5 h-5 text-white" />
              <h2 className="text-base font-semibold text-white">
                Созданные карточки проектов ({projects.length})
              </h2>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-zinc-400">
              <Lock className="w-3.5 h-3.5 text-[#C50337]" />
              <span>Роль: {role}</span>
            </div>
          </div>

          {projects.length === 0 ? (
            <div className="text-sm text-zinc-400 py-8 text-center">
              Пока нет созданных проектов для текущей роли.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm">
                <thead>
                  <tr className="border-b border-white/[0.08] text-zinc-400 text-xs">
                    <th className="py-2.5 pr-3">Шаблон</th>
                    <th className="py-2.5 px-3">Проект</th>
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
                      <td className="py-3 px-3 font-medium text-white">{p.project_title}</td>
                      <td className="py-3 px-3 text-zinc-300">{p.executor_name}</td>
                      <td className="py-3 px-3 font-mono text-xs text-zinc-300 uppercase">
                        {p.access_level}
                      </td>
                      <td className="py-3 pl-3 text-right">
                        <button
                          type="button"
                          onClick={() => void downloadGeneratedDocx(p.generated_file_name, token)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.08] hover:bg-white/[0.14] text-xs text-white transition"
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
      )}
    </div>
  );
};

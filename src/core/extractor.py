"""Extractor module for regulatory documents, matrix, guidelines, terms, and modular templates.

Extracts structured chapters, clauses, page numbers, clean text, glossaries,
and dynamic template schemas from PDF and DOCX files.
"""

from dataclasses import dataclass, field
import hashlib
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import unicodedata

import docx
import pymupdf

logger = logging.getLogger(__name__)

WATERMARK_TEXT = "УЧЕБНЫЙ ПРИМЕР ДЛЯ ИТ-СОРЕВНОВАНИЙ. НЕ ЯВЛЯЕТСЯ ДЕЙСТВУЮЩИМ ДОКУМЕНТОМ"


@dataclass
class ExtractedChunk:
    """Granular chunk of a document with citation metadata."""
    chapter: str
    clause: str
    page_number: int
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedDocument:
    """Full document representation ready for database persistence."""
    doc_code: str
    title: str
    doc_type: str
    version: str
    access_level: str
    file_name: str
    file_size: int
    sha256: str
    chunks: List[ExtractedChunk] = field(default_factory=list)


@dataclass
class DefinedTermDTO:
    """Canonical term or abbreviation definition."""
    canonical: str
    expansion: str
    definition: Optional[str]
    source_doc_code: str = "OD-184"
    clause: Optional[str] = "1.4"
    page_number: Optional[int] = 2


@dataclass
class ApprovalRuleDTO:
    """Approval matrix rule with condition branches."""
    rule_number: int
    category: str
    doc_type_name: str
    is_modular: bool
    requires_legal: bool
    requires_dou: bool
    requires_hr: bool
    requires_infosec: str
    requires_it: str
    requires_regional: str
    condition_description: Optional[str]
    signatory: str
    extra_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TemplateModuleDTO:
    """Modular document template with dynamic field schema."""
    module_code: str
    doc_kind: str
    title: str
    reg_number: str
    version: str
    file_name: str
    fields_schema: List[Dict[str, Any]]
    default_rule_number: int
    chunks: List[ExtractedChunk] = field(default_factory=list)


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_unicode(text: str) -> str:
    """Normalize unicode characters to NFC form."""
    return unicodedata.normalize("NFC", text)


def clean_pdf_text_line(line: str) -> Optional[str]:
    """Clean and filter out watermarks or empty lines."""
    line_clean = line.strip()
    if not line_clean:
        return None
    if line_clean == WATERMARK_TEXT or WATERMARK_TEXT in line_clean:
        return None
    return line_clean


def extract_pdf_instruction(pdf_path: Path) -> ExtractedDocument:
    """Parse the main DOU Instruction PDF (51 pages) into granular chunks.
    
    Tracks:
    - chapter: Full chapter heading (e.g. 'Глава 4. Полномочия участников...')
    - clause: Clause identifier (e.g. '4.2.3', '10.6')
    - page_number: 1-based page number where the clause appears
    - content: Clean text without watermarks
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    file_size = pdf_path.stat().st_size
    sha256 = compute_file_hash(pdf_path)
    file_name = normalize_unicode(pdf_path.name)

    doc = pymupdf.open(pdf_path)
    chunks: List[ExtractedChunk] = []

    current_chapter = "Титульный лист и общие сведения"
    current_chapter_num = 0
    current_clause = "Титул"
    current_clause_page = 1
    current_lines: List[str] = []

    for p_idx in range(len(doc)):
        page_num = p_idx + 1
        page_text = doc[p_idx].get_text()
        raw_lines = page_text.split("\n")

        cleaned_lines: List[str] = []
        for l in raw_lines:
            c = clean_pdf_text_line(l)
            if c:
                cleaned_lines.append(c)

        i = 0
        while i < len(cleaned_lines):
            line = cleaned_lines[i]

            # Detect Chapter Header: "Глава X. Title..."
            m_ch = re.match(r"^(?:Глава|ГЛАВА)\s+(\d+)\.(.*)", line, re.I)
            if m_ch:
                current_chapter_num = int(m_ch.group(1))
                ch_title = f"Глава {current_chapter_num}.{m_ch.group(2)}"
                # If chapter title continues on subsequent line before next clause
                if (
                    i + 1 < len(cleaned_lines)
                    and not re.match(r"^\d+\.\d+", cleaned_lines[i + 1])
                    and not re.match(r"^(?:Глава|ГЛАВА)", cleaned_lines[i + 1], re.I)
                ):
                    ch_title += " " + cleaned_lines[i + 1]
                    i += 1
                current_chapter = " ".join(ch_title.split())
                i += 1
                continue

            # Detect Appendix Header: "Приложение № X..."
            m_app = re.match(r"^(Приложение\s+№\s*\d+.*)", line, re.I)
            if m_app:
                if current_lines:
                    content_str = "\n".join(current_lines).strip()
                    if content_str:
                        chunks.append(
                            ExtractedChunk(
                                chapter=current_chapter,
                                clause=current_clause,
                                page_number=current_clause_page,
                                content=content_str,
                                metadata={
                                    "doc_code": "OD-184",
                                    "chapter_num": current_chapter_num,
                                    "clause": current_clause,
                                    "page": current_clause_page,
                                },
                            )
                        )
                current_chapter = "Приложения"
                current_clause = m_app.group(1).strip()
                current_clause_page = page_num
                current_lines = cleaned_lines[i:]
                break

            # Detect Clause Header: "X.Y" or "X.Y.Z"
            m_cl = re.match(r"^(\d+\.\d+(?:\.\d+)?)\.?\s*(.*)", line)
            is_new_clause = False
            if m_cl:
                cl_major = int(m_cl.group(1).split(".")[0])
                # Ensure clause major matches current chapter to prevent mid-sentence wrapping errors
                if cl_major == current_chapter_num:
                    is_new_clause = True

            if is_new_clause:
                assert m_cl is not None
                if current_lines:
                    content_str = "\n".join(current_lines).strip()
                    if content_str:
                        chunks.append(
                            ExtractedChunk(
                                chapter=current_chapter,
                                clause=current_clause,
                                page_number=current_clause_page,
                                content=content_str,
                                metadata={
                                    "doc_code": "OD-184",
                                    "chapter_num": current_chapter_num,
                                    "clause": current_clause,
                                    "page": current_clause_page,
                                },
                            )
                        )
                current_clause = m_cl.group(1)
                current_clause_page = page_num
                current_lines = [line]
            else:
                current_lines.append(line)

            i += 1

    # Append remaining lines
    if current_lines:
        content_str = "\n".join(current_lines).strip()
        if content_str:
            chunks.append(
                ExtractedChunk(
                    chapter=current_chapter,
                    clause=current_clause,
                    page_number=current_clause_page,
                    content=content_str,
                    metadata={
                        "doc_code": "OD-184",
                        "chapter_num": current_chapter_num,
                        "clause": current_clause,
                        "page": current_clause_page,
                    },
                )
            )

    doc.close()
    logger.info(f"Successfully extracted {len(chunks)} chunks from PDF: {file_name}")

    return ExtractedDocument(
        doc_code="OD-184",
        title="Инструкция по документационному обеспечению управления и документообороту Организации",
        doc_type="instruction",
        version="1.0",
        access_level="public",
        file_name=file_name,
        file_size=file_size,
        sha256=sha256,
        chunks=chunks,
    )


def extract_defined_terms(pdf_doc: ExtractedDocument) -> List[DefinedTermDTO]:
    """Extract canonical terms and abbreviations from clause 1.4 of the instruction."""
    # Find chunk for clause 1.4
    clause_1_4_content = ""
    for c in pdf_doc.chunks:
        if c.clause == "1.4":
            clause_1_4_content = c.content
            break

    terms: List[DefinedTermDTO] = [
        # Explicit abbreviations from clause 1.4 & matrix
        DefinedTermDTO(
            canonical="ДОУ",
            expansion="Документационное обеспечение управления",
            definition="Деятельность, обеспечивающая документирование управленческих решений, организацию движения, учета, использования, контроля исполнения, оперативного и архивного хранения документов.",
            clause="1.4",
            page_number=2,
        ),
        DefinedTermDTO(
            canonical="ИИС ДО",
            expansion="Интегрированная информационная система документационного обеспечения",
            definition="Информационная система, обеспечивающая полный жизненный цикл документов и проектов документов Организации.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="ЭД",
            expansion="Электронный документ",
            definition="Документированная информация в электронной форме, созданная без предварительного документирования на бумажном носителе и подписанная электронной подписью.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="ЭКД",
            expansion="Электронная копия документа",
            definition="Электронный образ бумажного документа, воспроизводящий его содержание и внешние признаки и не заменяющий оригинал, если иное не установлено законодательством РФ.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="ПД",
            expansion="Проект документа",
            definition="Документ до его подписания или утверждения уполномоченным должностным лицом.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="РК",
            expansion="Регистрационная карточка",
            definition="Визуальное представление в ИИС ДО реквизитов документа или проекта документа и его метаданных, включая сведения о ходе работы.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="ЭП",
            expansion="Электронная подпись",
            definition="Информация в электронной форме, присоединенная к подписываемой информации или иным образом связанная с ней и используемая для определения подписавшего лица.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="РБД",
            expansion="Реестр бумажного документооборота",
            definition="Учетная форма для фиксации движения документов на бумажном носителе.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="СП ЦА",
            expansion="Структурные подразделения Центрального аппарата",
            definition="Департаменты, управления и иные предусмотренные приказом о структуре Организации самостоятельные подразделения Центрального аппарата.",
            clause="1.4",
            page_number=2,
        ),
        DefinedTermDTO(
            canonical="РО Организации",
            expansion="Региональные отделения Организации",
            definition="Обособленные подразделения Организации, осуществляющие функции Организации на закрепленной территории.",
            clause="1.4",
            page_number=2,
        ),
        DefinedTermDTO(
            canonical="РО",
            expansion="Региональное отделение Организации",
            definition="Обособленное подразделение Организации, осуществляющее функции Организации на закрепленной территории (примечание к Матрице визирования, п. 1.4 Инструкции).",
            clause="1.4",
            page_number=2,
        ),
        DefinedTermDTO(
            canonical="СП РО",
            expansion="Структурные подразделения РО Организации",
            definition="Управления, отделы, секторы, центры и иные организационные единицы, входящие в структуру РО Организации.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="СП",
            expansion="Структурное подразделение",
            definition="Структурное подразделение Центрального аппарата или регионального отделения Организации (примечание к Матрице визирования, п. 1.4 Инструкции).",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="ЦА",
            expansion="Центральный аппарат",
            definition="Центральный аппарат Организации, включающий руководство и самостоятельные структурные подразделения.",
            clause="1.4",
            page_number=2,
        ),
        DefinedTermDTO(
            canonical="ЛНА",
            expansion="Локальный нормативный акт",
            definition="Внутренний нормативный документ Организации (положение, регламент, правила, инструкция, порядок), утверждаемый приказом руководства Организации.",
            clause="1.5, 9.5",
            page_number=4,
        ),
        DefinedTermDTO(
            canonical="ДСП",
            expansion="Для служебного пользования",
            definition="Гриф ограничения доступа к служебной информации ограниченного распространения, проставляемый в правом верхнем углу первой страницы документа.",
            clause="8.2, 8.13",
            page_number=26,
        ),
        DefinedTermDTO(
            canonical="ИС",
            expansion="Информационная система",
            definition="Информационная система Организации (примечание к Матрице обязательного визирования).",
            clause="Матрица",
            page_number=1,
        ),
        DefinedTermDTO(
            canonical="ИТ",
            expansion="Информационные технологии",
            definition="Информационные технологии (примечание к Матрице обязательного визирования).",
            clause="Матрица",
            page_number=1,
        ),
        DefinedTermDTO(
            canonical="Руководство Организации",
            expansion="Руководство Организации",
            definition="Председатель Организации и заместители Председателя Организации.",
            clause="1.4",
            page_number=2,
        ),
        DefinedTermDTO(
            canonical="Заместители Председателя Организации",
            expansion="Заместители Председателя Организации",
            definition="Должностные лица, замещающие должности заместителей Председателя Организации и осуществляющие полномочия в соответствии с распределением обязанностей.",
            clause="1.4",
            page_number=2,
        ),
        DefinedTermDTO(
            canonical="Подразделения ДОУ",
            expansion="Подразделения документационного обеспечения управления",
            definition="Департамент документационного обеспечения Центрального аппарата (Департамент ДОУ), а в РО Организации — СП РО, на которые возложены функции ДОУ.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="Служба ДОУ",
            expansion="Служба документационного обеспечения управления",
            definition="Совокупность подразделений ДОУ и работников, ответственных за ДОУ в Центральном аппарате и РО Организации.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="Подразделения Организации",
            expansion="Подразделения Организации",
            definition="СП ЦА, РО Организации и СП РО.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="Метаданные",
            expansion="Метаданные документа",
            definition="Структурированные сведения о документе, его реквизитах, состоянии, связях и операциях, выполняемых с ним.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="Лингвистическая экспертиза",
            expansion="Лингвистическая экспертиза",
            definition="Проверка текста на соответствие нормам русского языка, требованиям точности, однозначности, единства терминологии, официально-делового стиля и оформления.",
            clause="1.4, 10.6",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="Внешний адресат",
            expansion="Внешний адресат",
            definition="Физическое лицо, юридическое лицо, орган государственной власти или иная организация, не входящие в структуру Организации.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="Органы государственной власти",
            expansion="Органы государственной власти",
            definition="Федеральные органы государственной власти, органы государственной власти субъектов Российской Федерации и иные государственные органы, образованные в соответствии с законодательством РФ.",
            clause="1.4",
            page_number=2,
        ),
        DefinedTermDTO(
            canonical="Матрица маршрутизации документов по функциям Организации",
            expansion="Матрица маршрутизации документов по функциям Организации",
            definition="Утвержденный Департаментом ДОУ справочник соответствия тем, видов вопросов и функций ответственным подразделениям, соисполнителям и подразделениям, информируемым о документе.",
            clause="1.4",
            page_number=3,
        ),
        DefinedTermDTO(
            canonical="Матрица обязательного визирования",
            expansion="Матрица обязательного визирования",
            definition="Утвержденный Департаментом ДОУ справочник обязательных согласующих и визирующих в зависимости от вида, содержания и предмета проекта документа.",
            clause="1.4, 10.11",
            page_number=3,
        ),
    ]

    return terms


def extract_guidelines_document(docx_path: Path) -> ExtractedDocument:
    """Parse Methodological Guidelines DOCX into structured search chunks."""
    if not docx_path.exists():
        raise FileNotFoundError(f"Guidelines file not found: {docx_path}")

    file_size = docx_path.stat().st_size
    sha256 = compute_file_hash(docx_path)
    file_name = normalize_unicode(docx_path.name)

    doc = docx.Document(docx_path)
    chunks: List[ExtractedChunk] = []

    current_section = "Введение"
    current_clause = "Общие сведения"
    clause_lines: List[str] = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Major section: "1. Общие положения", "2. Создание регистрационной карточки..."
        m_sec = re.match(r"^(\d+)\.\s+([А-Яа-яA-Za-z].*)", text)
        m_cl = re.match(r"^(\d+\.\d+)\.?\s*(.*)", text)

        if m_sec and not m_cl:
            if clause_lines:
                chunks.append(
                    ExtractedChunk(
                        chapter=current_section,
                        clause=current_clause,
                        page_number=1,
                        content="\n".join(clause_lines),
                        metadata={
                            "doc_code": "METHOD-GUIDELINES",
                            "section": current_section,
                            "clause": current_clause,
                        },
                    )
                )
                clause_lines = []
            current_section = f"Раздел {m_sec.group(1)}. {m_sec.group(2)}"
            current_clause = f"Раздел {m_sec.group(1)}"
            clause_lines = [text]
        elif m_cl:
            if clause_lines:
                chunks.append(
                    ExtractedChunk(
                        chapter=current_section,
                        clause=current_clause,
                        page_number=1,
                        content="\n".join(clause_lines),
                        metadata={
                            "doc_code": "METHOD-GUIDELINES",
                            "section": current_section,
                            "clause": current_clause,
                        },
                    )
                )
            current_clause = m_cl.group(1)
            clause_lines = [text]
        else:
            clause_lines.append(text)

    if clause_lines:
        chunks.append(
            ExtractedChunk(
                chapter=current_section,
                clause=current_clause,
                page_number=1,
                content="\n".join(clause_lines),
                metadata={
                    "doc_code": "METHOD-GUIDELINES",
                    "section": current_section,
                    "clause": current_clause,
                },
            )
        )

    return ExtractedDocument(
        doc_code="METHOD-GUIDELINES",
        title="Методические рекомендации по работе с модульными документами",
        doc_type="guideline",
        version="1.0",
        access_level="public",
        file_name=file_name,
        file_size=file_size,
        sha256=sha256,
        chunks=chunks,
    )


def extract_approval_matrix_data(
    docx_path: Path,
) -> tuple[ExtractedDocument, List[ApprovalRuleDTO]]:
    """Extract approval rules and search chunks from Approval Matrix DOCX."""
    if not docx_path.exists():
        raise FileNotFoundError(f"Matrix file not found: {docx_path}")

    file_size = docx_path.stat().st_size
    sha256 = compute_file_hash(docx_path)
    file_name = normalize_unicode(docx_path.name)

    doc = docx.Document(docx_path)
    chunks: List[ExtractedChunk] = []

    # Introductory chunk from paragraphs
    intro_lines: List[str] = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    chunks.append(
        ExtractedChunk(
            chapter="Матрица обязательного визирования: общие положения",
            clause="Вводная часть",
            page_number=1,
            content="\n".join(intro_lines),
            metadata={"doc_code": "APPROVAL-MATRIX", "type": "intro"},
        )
    )

    rules: List[ApprovalRuleDTO] = [
        ApprovalRuleDTO(
            rule_number=1,
            category="internal",
            doc_type_name="Приказы о работе в выходные и нерабочие праздничные дни, а также по иным вопросам рабочего календаря, подготовленные с использованием модульных документов",
            is_modular=True,
            requires_legal=True,
            requires_dou=True,
            requires_hr=True,
            requires_infosec="no",
            requires_it="no",
            requires_regional="no",
            condition_description="Обязательное визирование: Юридическое подразделение, Департамент ДОУ, Кадровое подразделение.",
            signatory="Руководство Организации / Заместитель Председателя",
            extra_info={
                "matrix_section": "internal",
                "matrix_row": 1,
                "departments": ["Юридическое подразделение", "Департамент ДОУ", "Кадровое подразделение"],
            },
        ),
        ApprovalRuleDTO(
            rule_number=2,
            category="internal",
            doc_type_name="Приказы о приеме и передаче дел и имущества при назначении, освобождении от должности, реорганизации и иных кадровых изменениях (без изменения доступа к ИС), подготовленные с использованием модульных документов",
            is_modular=True,
            requires_legal=True,
            requires_dou=True,
            requires_hr=True,
            requires_infosec="no",
            requires_it="no",
            requires_regional="no",
            condition_description="Стандартный маршрут: Юридическое подразделение, Департамент ДОУ, Кадровое подразделение (без затрагивания прав доступа к ИС).",
            signatory="Руководство Организации / Руководитель подразделения",
            extra_info={
                "matrix_section": "internal",
                "matrix_row": 2,
                "involves_infosec_access": False,
                "departments": ["Юридическое подразделение", "Департамент ДОУ", "Кадровое подразделение"],
            },
        ),
        ApprovalRuleDTO(
            rule_number=3,
            category="internal",
            doc_type_name="Приказы о приеме и передаче дел и имущества при назначении, освобождении от должности, реорганизации и иных кадровых изменениях (с изменением доступа к ИС), подготовленные с использованием модульных документов",
            is_modular=True,
            requires_legal=True,
            requires_dou=True,
            requires_hr=True,
            requires_infosec="yes",
            requires_it="no",
            requires_regional="no",
            condition_description="Департамент информационной безопасности визирует проект, если прием и передача дел связаны с предоставлением, изменением или прекращением доступа к информационным системам.",
            signatory="Руководство Организации / Руководитель подразделения",
            extra_info={
                "matrix_section": "internal",
                "matrix_row": 2,
                "involves_infosec_access": True,
                "departments": ["Юридическое подразделение", "Департамент ДОУ", "Кадровое подразделение", "Департамент информационной безопасности"],
            },
        ),
        ApprovalRuleDTO(
            rule_number=4,
            category="internal",
            doc_type_name="Приказы по вопросам информационных систем, включая ввод в эксплуатацию, вывод из эксплуатации, опытную эксплуатацию, изменение компонентов и иные связанные вопросы, подготовленные с использованием модульных документов",
            is_modular=True,
            requires_legal=True,
            requires_dou=True,
            requires_hr=False,
            requires_infosec="yes",
            requires_it="yes",
            requires_regional="no",
            condition_description="Обязательное визирование: Юридическое подразделение, Департамент ДОУ, Департамент информационной безопасности, Департамент информационных технологий.",
            signatory="Руководство Организации / Заместитель Председателя",
            extra_info={
                "matrix_section": "internal",
                "matrix_row": 3,
                "involves_it": True,
                "involves_infosec_access": True,
                "departments": ["Юридическое подразделение", "Департамент ДОУ", "Департамент информационной безопасности", "Департамент информационных технологий"],
            },
        ),
        ApprovalRuleDTO(
            rule_number=5,
            category="internal",
            doc_type_name="Прочие приказы, в т.ч., подготовленные без использования модульных документов или с использованием модульных документов кроме указанных в пп.1-3 (включая назначение ответственных за ДОУ и утверждение ЛНА)",
            is_modular=False,
            requires_legal=True,
            requires_dou=True,
            requires_hr=False,
            requires_infosec="no",
            requires_it="no",
            requires_regional="no",
            condition_description="Обязательное визирование: Юридическое подразделение, Департамент ДОУ. Подразделение, компетенция которого затрагивается, включается в маршрут независимо от отдельной отметки.",
            signatory="Руководство Организации",
            extra_info={
                "matrix_section": "internal",
                "matrix_row": 4,
                "departments": ["Юридическое подразделение", "Департамент ДОУ"],
            },
        ),
        ApprovalRuleDTO(
            rule_number=6,
            category="internal",
            doc_type_name="Распоряжения о предоставлении материальной помощи и осуществлении иных выплат работникам",
            is_modular=False,
            requires_legal=False,
            requires_dou=True,
            requires_hr=True,
            requires_infosec="no",
            requires_it="no",
            requires_regional="no",
            condition_description="Визируется Департаментом ДОУ и Кадровым подразделением. Юридическое подразделение не требуется.",
            signatory="Руководство Организации / Заместитель Председателя",
            extra_info={
                "matrix_section": "internal",
                "matrix_row": 5,
                "departments": ["Департамент ДОУ", "Кадровое подразделение"],
            },
        ),
        ApprovalRuleDTO(
            rule_number=7,
            category="internal",
            doc_type_name="Распоряжения о создании рабочих групп, проектных комитетов, комиссий и иных временных объединений (общего профиля)",
            is_modular=True,
            requires_legal=False,
            requires_dou=True,
            requires_hr=True,
            requires_infosec="no",
            requires_it="no",
            requires_regional="no",
            condition_description="Визируется Департаментом ДОУ и Кадровым подразделением (если объединение не связано с ИТ-проектами).",
            signatory="Руководство Организации / Курирующий Заместитель Председателя",
            extra_info={
                "matrix_section": "internal",
                "matrix_row": 6,
                "involves_it": False,
                "departments": ["Департамент ДОУ", "Кадровое подразделение"],
            },
        ),
        ApprovalRuleDTO(
            rule_number=8,
            category="internal",
            doc_type_name="Распоряжения о создании рабочих групп, проектных комитетов, комиссий и иных временных объединений для реализации ИТ-проектов или вопросов ИС",
            is_modular=True,
            requires_legal=False,
            requires_dou=True,
            requires_hr=True,
            requires_infosec="no",
            requires_it="yes",
            requires_regional="no",
            condition_description="Департамент информационных технологий визирует проект, если временное объединение создается для реализации ИТ-проекта или решения вопросов информационных систем.",
            signatory="Руководство Организации / Курирующий Заместитель Председателя",
            extra_info={
                "matrix_section": "internal",
                "matrix_row": 6,
                "involves_it": True,
                "departments": ["Департамент ДОУ", "Кадровое подразделение", "Департамент информационных технологий"],
            },
        ),
        ApprovalRuleDTO(
            rule_number=9,
            category="internal",
            doc_type_name="Прочие распоряжения, подготовленные без использования модульных документов или с использованием модульных документов кроме указанных в пп.5-6 (включая проведение внутреннего аудита процессов)",
            is_modular=False,
            requires_legal=True,
            requires_dou=True,
            requires_hr=False,
            requires_infosec="no",
            requires_it="no",
            requires_regional="no",
            condition_description="Обязательное визирование: Юридическое подразделение, Департамент ДОУ.",
            signatory="Руководство Организации / Руководитель подразделения",
            extra_info={
                "matrix_section": "internal",
                "matrix_row": 7,
                "departments": ["Юридическое подразделение", "Департамент ДОУ"],
            },
        ),
        ApprovalRuleDTO(
            rule_number=10,
            category="external",
            doc_type_name="Письма за подписью Руководства Организации, адресуемые органам государственной власти, Администрации Президента РФ, членам Совета Федерации, депутатам Государственной Думы, Аппарату Правительства РФ, Счетной палате РФ",
            is_modular=False,
            requires_legal=True,
            requires_dou=True,
            requires_hr=False,
            requires_infosec="no",
            requires_it="no",
            requires_regional="no",
            condition_description="Обязательное визирование: Юридическое подразделение, Департамент ДОУ, Департамент внутреннего контроля.",
            signatory="Председатель Организации / Заместитель Председателя",
            extra_info={
                "matrix_section": "external",
                "matrix_row": 1,
                "departments": ["Юридическое подразделение", "Департамент ДОУ", "Департамент внутреннего контроля"],
            },
        ),
        ApprovalRuleDTO(
            rule_number=11,
            category="external",
            doc_type_name="Письма за подписью Руководства Организации, адресуемые руководству иностранных организаций, центральных (национальных) банков иностранных государств, а также международных банков и иных международных организаций",
            is_modular=False,
            requires_legal=True,
            requires_dou=True,
            requires_hr=False,
            requires_infosec="no",
            requires_it="no",
            requires_regional="no",
            condition_description="Обязательное визирование: Юридическое подразделение, Департамент ДОУ, Департамент международного сотрудничества.",
            signatory="Председатель Организации / Заместитель Председателя",
            extra_info={
                "matrix_section": "external",
                "matrix_row": 2,
                "departments": ["Юридическое подразделение", "Департамент ДОУ", "Департамент международного сотрудничества"],
            },
        ),
        ApprovalRuleDTO(
            rule_number=12,
            category="external",
            doc_type_name="Письма российским юридическим лицам за подписью Руководства Организации или руководителей СП ЦА",
            is_modular=False,
            requires_legal=True,
            requires_dou=True,
            requires_hr=False,
            requires_infosec="no",
            requires_it="no",
            requires_regional="no",
            condition_description="Обязательное визирование: Юридическое подразделение, Департамент ДОУ.",
            signatory="Руководство Организации / Руководитель СП",
            extra_info={
                "matrix_section": "external",
                "matrix_row": 3,
                "involves_regional": False,
                "departments": ["Юридическое подразделение", "Департамент ДОУ"],
            },
        ),
        ApprovalRuleDTO(
            rule_number=13,
            category="external",
            doc_type_name="Письма российским юридическим лицам за подписью руководства РО Организации (с участием региональных отделений)",
            is_modular=False,
            requires_legal=True,
            requires_dou=True,
            requires_hr=False,
            requires_infosec="no",
            requires_it="no",
            requires_regional="yes",
            condition_description="Визируется Юридическим подразделением, Департаментом ДОУ и службой документационного обеспечения РО Организации.",
            signatory="Руководитель РО Организации",
            extra_info={
                "matrix_section": "external",
                "matrix_row": 3,
                "involves_regional": True,
                "departments": ["Юридическое подразделение", "Департамент ДОУ", "Подразделение ДОУ РО Организации"],
            },
        ),
    ]

    # Generate search chunks for each rule to empower full-text search
    for r in rules:
        dept_str = ", ".join(r.extra_info.get("departments", []))
        content = (
            f"Правило визирования № {r.rule_number} ({'Внутренний документ' if r.category == 'internal' else 'Внешний документ'}):\n"
            f"Вид документа: {r.doc_type_name}\n"
            f"Модульный документ: {'Да' if r.is_modular else 'Нет'}\n"
            f"Обязательные согласующие: Юридическое ({'Да' if r.requires_legal else 'Нет'}), "
            f"Департамент ДОУ ({'Да' if r.requires_dou else 'Нет'}), "
            f"Кадровое ({'Да' if r.requires_hr else 'Нет'}), "
            f"Департамент ИБ ({r.requires_infosec}), "
            f"Департамент ИТ ({r.requires_it}), "
            f"РО ({r.requires_regional}).\n"
            f"Согласующие подразделения: {dept_str}.\n"
            f"Условия визирования: {r.condition_description or 'Стандартный маршрут'}.\n"
            f"Подписант: {r.signatory}."
        )
        chunks.append(
            ExtractedChunk(
                chapter=f"Матрица визирования: {'Внутренние' if r.category == 'internal' else 'Внешние'} документы",
                clause=f"Правило {r.rule_number}",
                page_number=1,
                content=content,
                metadata={
                    "doc_code": "APPROVAL-MATRIX",
                    "rule_number": r.rule_number,
                    "category": r.category,
                },
            )
        )

    matrix_doc = ExtractedDocument(
        doc_code="APPROVAL-MATRIX",
        title="Матрица обязательного визирования проектов внутренних и внешних документов Организации",
        doc_type="matrix",
        version="1.0",
        access_level="public",
        file_name=file_name,
        file_size=file_size,
        sha256=sha256,
        chunks=chunks,
    )

    return matrix_doc, rules


def extract_template_modules(materials_dir: Path) -> List[TemplateModuleDTO]:
    """Inspect and register all 7 modular templates with dynamic field schemas."""
    # Mapping definitions
    configs = [
        {
            "pattern": "*вводе_в_эксплуатацию*",
            "module_code": "MOD-ORDER-IS",
            "doc_kind": "Приказ",
            "title": "Приказ о вводе в эксплуатацию информационной системы",
            "reg_number": "УТВ-01",
            "default_rule_number": 4,
            "fields": [
                {
                    "name": "system_name",
                    "label": "Наименование информационной системы",
                    "type": "string",
                    "required": True,
                    "description": "Полное и точное официальное наименование ИС",
                },
                {
                    "name": "purpose",
                    "label": "Цель ввода в эксплуатацию",
                    "type": "string",
                    "required": True,
                    "description": "Обоснование и цели: автоматизация, повышение надежности и т.д.",
                },
                {
                    "name": "commissioning_date",
                    "label": "Дата ввода в эксплуатацию",
                    "type": "date",
                    "required": True,
                    "description": "Дата начала постоянной эксплуатации информационной системы",
                },
                {
                    "name": "responsible_dept",
                    "label": "Ответственное подразделение",
                    "type": "string",
                    "required": True,
                    "description": "Структурное подразделение, ответственное за сопровождение",
                },
                {
                    "name": "infosec_dept",
                    "label": "Подразделение информационной безопасности",
                    "type": "string",
                    "required": True,
                    "description": "Подразделение, обеспечивающее контроль ИБ системы",
                },
                {
                    "name": "control_officer",
                    "label": "Контроль исполнения",
                    "type": "string",
                    "required": False,
                    "default": "Контроль за исполнением настоящего приказа оставляю за собой",
                    "description": "Должность и ФИО лица, на которое возложен контроль",
                },
            ],
        },
        {
            "pattern": "*назначении_ответственных*",
            "module_code": "MOD-ORDER-DOU",
            "doc_kind": "Приказ",
            "title": "Приказ о назначении ответственных за делопроизводство и документооборот",
            "reg_number": "УТВ-02",
            "default_rule_number": 5,
            "fields": [
                {
                    "name": "department_name",
                    "label": "Структурное подразделение",
                    "type": "string",
                    "required": True,
                    "description": "Полное наименование подразделения Организации",
                },
                {
                    "name": "primary_responsible",
                    "label": "Основной ответственный работник",
                    "type": "string",
                    "required": True,
                    "description": "Должность, структурное подразделение и ФИО работника",
                },
                {
                    "name": "deputy_responsible",
                    "label": "Замещающий ответственный работник",
                    "type": "string",
                    "required": True,
                    "description": "Должность, подразделение и ФИО лица на период отсутствия основного",
                },
                {
                    "name": "reason",
                    "label": "Основание назначения",
                    "type": "string",
                    "required": True,
                    "description": "Цели надлежащей организации ДОУ, кадровые перестановки и т.д.",
                },
                {
                    "name": "control_officer",
                    "label": "Контроль исполнения",
                    "type": "string",
                    "required": False,
                    "default": "Контроль за исполнением настоящего приказа оставляю за собой",
                    "description": "Должность и ФИО лица, контролирующего исполнение приказа",
                },
            ],
        },
        {
            "pattern": "*приеме_и_передаче*",
            "module_code": "MOD-ORDER-PROP",
            "doc_kind": "Приказ",
            "title": "Приказ о приеме и передаче дел и имущества",
            "reg_number": "УТВ-03",
            "default_rule_number": 2,
            "fields": [
                {
                    "name": "department_name",
                    "label": "Структурное подразделение",
                    "type": "string",
                    "required": True,
                    "description": "Подразделение, в котором происходит передача дел",
                },
                {
                    "name": "transferor_name",
                    "label": "Передающее лицо (ФИО, должность)",
                    "type": "string",
                    "required": True,
                    "description": "Работник, сдающий дела и имущество",
                },
                {
                    "name": "transferee_name",
                    "label": "Принимающее лицо (ФИО, должность)",
                    "type": "string",
                    "required": True,
                    "description": "Работник, принимающий дела и имущество",
                },
                {
                    "name": "transfer_basis",
                    "label": "Основание передачи",
                    "type": "string",
                    "required": True,
                    "description": "Причина передачи: перевод, освобождение от должности, реорганизация",
                },
                {
                    "name": "deadline",
                    "label": "Срок передачи",
                    "type": "date",
                    "required": True,
                    "description": "Конечный срок подписания акта приема-передачи",
                },
                {
                    "name": "commission_members",
                    "label": "Члены комиссии",
                    "type": "textarea",
                    "required": False,
                    "description": "Состав комиссии по приему-передаче дел (при наличии)",
                },
                {
                    "name": "affects_is_access",
                    "label": "Изменение доступа к ИС",
                    "type": "boolean",
                    "required": True,
                    "default": False,
                    "description": "Требуется ли виза Департамента ИБ в связи с правами доступа к ИС",
                },
                {
                    "name": "control_officer",
                    "label": "Контроль исполнения",
                    "type": "string",
                    "required": False,
                    "default": "Контроль за исполнением настоящего приказа оставляю за собой",
                    "description": "Должностное лицо, контролирующее передачу",
                },
            ],
        },
        {
            "pattern": "*локального*",
            "module_code": "MOD-ORDER-LNA",
            "doc_kind": "Приказ",
            "title": "Приказ об утверждении и введении в действие локального нормативного акта",
            "reg_number": "УТВ-04",
            "default_rule_number": 5,
            "fields": [
                {
                    "name": "act_title",
                    "label": "Наименование утверждаемого документа",
                    "type": "string",
                    "required": True,
                    "description": "Полное наименование ЛНА (положение, правила, регламент, инструкция)",
                },
                {
                    "name": "purpose",
                    "label": "Цель издания приказа",
                    "type": "string",
                    "required": True,
                    "description": "Обоснование: совершенствование процессов, выполнение требований законодательства",
                },
                {
                    "name": "effective_date",
                    "label": "Дата введения в действие",
                    "type": "date",
                    "required": True,
                    "description": "Дата начала применения локального нормативного акта",
                },
                {
                    "name": "responsible_dept",
                    "label": "Ответственное подразделение",
                    "type": "string",
                    "required": True,
                    "description": "Подразделение, обеспечивающее ознакомление и размещение документа",
                },
                {
                    "name": "placement_location",
                    "label": "Место размещения",
                    "type": "string",
                    "required": True,
                    "default": "внутренний информационный портал Организации",
                    "description": "Официальный корпоративный ресурс для публикации ЛНА",
                },
                {
                    "name": "repeal_act",
                    "label": "Отменяемый документ",
                    "type": "string",
                    "required": False,
                    "description": "Реквизиты ранее действовавшего документа, признаваемого утратившим силу",
                },
                {
                    "name": "control_officer",
                    "label": "Контроль исполнения",
                    "type": "string",
                    "required": False,
                    "default": "Контроль за исполнением настоящего приказа оставляю за собой",
                    "description": "Должностное лицо, контролирующее исполнение",
                },
            ],
        },
        {
            "pattern": "*внутреннего_аудита*",
            "module_code": "MOD-DISP-AUDIT",
            "doc_kind": "Распоряжение",
            "title": "Распоряжение о проведении внутреннего аудита процессов",
            "reg_number": "УТВ-05",
            "default_rule_number": 9,
            "fields": [
                {
                    "name": "audit_process",
                    "label": "Наименование процесса аудита",
                    "type": "string",
                    "required": True,
                    "description": "Процесс или процессы Организации, подлежащие аудиту",
                },
                {
                    "name": "audit_goal",
                    "label": "Цель аудита",
                    "type": "string",
                    "required": True,
                    "description": "Оценка соответствия, выявление рисков, анализ эффективности",
                },
                {
                    "name": "audit_period",
                    "label": "Сроки проведения аудита",
                    "type": "string",
                    "required": True,
                    "description": "Период проверки (например, с 01 по 20 ноября 2026 г.)",
                },
                {
                    "name": "audited_dept",
                    "label": "Проверяемое подразделение",
                    "type": "string",
                    "required": True,
                    "description": "Структурное подразделение Организации, в котором проводится аудит",
                },
                {
                    "name": "audit_leader",
                    "label": "Руководитель группы аудита",
                    "type": "string",
                    "required": True,
                    "description": "Должность, подразделение и ФИО руководителя аудиторской группы",
                },
                {
                    "name": "audit_team",
                    "label": "Состав группы аудита",
                    "type": "textarea",
                    "required": True,
                    "description": "Перечень членов группы аудита (должности, ФИО)",
                },
                {
                    "name": "report_deadline",
                    "label": "Срок предоставления отчета",
                    "type": "date",
                    "required": True,
                    "description": "Дата представления итогового аудиторского отчета руководству",
                },
                {
                    "name": "control_officer",
                    "label": "Контроль исполнения",
                    "type": "string",
                    "required": False,
                    "default": "Контроль за исполнением настоящего распоряжения оставляю за собой",
                    "description": "Должностное лицо, контролирующее исполнение распоряжения",
                },
            ],
        },
        {
            "pattern": "*проектного_комитета*",
            "module_code": "MOD-DISP-PROJECT",
            "doc_kind": "Распоряжение",
            "title": "Распоряжение о создании проектного комитета",
            "reg_number": "УТВ-06",
            "default_rule_number": 7,
            "fields": [
                {
                    "name": "project_name",
                    "label": "Наименование проекта (проектов)",
                    "type": "string",
                    "required": True,
                    "description": "Полное наименование одного или нескольких проектов",
                },
                {
                    "name": "committee_purpose",
                    "label": "Цель создания Комитета",
                    "type": "string",
                    "required": True,
                    "description": "Координация деятельности участников проекта и контроль сроков",
                },
                {
                    "name": "reason",
                    "label": "Основание создания",
                    "type": "string",
                    "required": True,
                    "description": "Обстоятельство: запуск проекта, изменение этапа, межфункциональное взаимодействие",
                },
                {
                    "name": "managing_dept",
                    "label": "Ответственное подразделение",
                    "type": "string",
                    "required": True,
                    "description": "Подразделение Организации, реализующее проект",
                },
                {
                    "name": "chairman",
                    "label": "Председатель Комитета",
                    "type": "string",
                    "required": True,
                    "description": "Должность, подразделение и ФИО председателя",
                },
                {
                    "name": "deputy_chairman",
                    "label": "Заместитель председателя Комитета",
                    "type": "string",
                    "required": False,
                    "description": "Должность, подразделение и ФИО заместителя (при наличии)",
                },
                {
                    "name": "secretary",
                    "label": "Секретарь Комитета",
                    "type": "string",
                    "required": True,
                    "description": "Должность, подразделение и ФИО секретаря Комитета",
                },
                {
                    "name": "members",
                    "label": "Члены Комитета",
                    "type": "textarea",
                    "required": True,
                    "description": "Список членов Комитета с указанием должностей и ФИО",
                },
                {
                    "name": "is_it_project",
                    "label": "ИТ-проект",
                    "type": "boolean",
                    "required": True,
                    "default": False,
                    "description": "Создается ли комитет для реализации ИТ-проекта (требуется виза ДИТ)",
                },
                {
                    "name": "repeal_order",
                    "label": "Отменяемое распоряжение",
                    "type": "string",
                    "required": False,
                    "description": "Дата и номер ранее изданного распоряжения (при отмене)",
                },
                {
                    "name": "control_officer",
                    "label": "Контроль исполнения",
                    "type": "string",
                    "required": False,
                    "default": "Контроль за исполнением настоящего распоряжения оставляю за собой",
                    "description": "Должностное лицо, на которое возложен контроль",
                },
            ],
        },
        {
            "pattern": "*рабочей_группы*",
            "module_code": "MOD-DISP-WORKGROUP",
            "doc_kind": "Распоряжение",
            "title": "Распоряжение о создании рабочей группы",
            "reg_number": "УТВ-07",
            "default_rule_number": 7,
            "fields": [
                {
                    "name": "workgroup_subject",
                    "label": "Предмет работы рабочей группы",
                    "type": "string",
                    "required": True,
                    "description": "Тема или предмет деятельности: подготовка документов, анализ и т.д.",
                },
                {
                    "name": "goal",
                    "label": "Цель рабочей группы",
                    "type": "string",
                    "required": True,
                    "description": "Практическая цель: внедрение изменения, выработка предложений и т.д.",
                },
                {
                    "name": "leader",
                    "label": "Руководитель рабочей группы",
                    "type": "string",
                    "required": True,
                    "description": "Должность, подразделение и ФИО руководителя группы",
                },
                {
                    "name": "deputy_leader",
                    "label": "Заместитель руководителя",
                    "type": "string",
                    "required": False,
                    "description": "Должность, подразделение и ФИО заместителя (при наличии)",
                },
                {
                    "name": "secretary",
                    "label": "Секретарь рабочей группы",
                    "type": "string",
                    "required": True,
                    "description": "Должность, подразделение и ФИО секретаря группы",
                },
                {
                    "name": "members",
                    "label": "Члены рабочей группы",
                    "type": "textarea",
                    "required": True,
                    "description": "Список участников (должности, подразделения, ФИО)",
                },
                {
                    "name": "deadline",
                    "label": "Срок выполнения",
                    "type": "date",
                    "required": True,
                    "description": "Конечный срок представления результатов",
                },
                {
                    "name": "expected_result",
                    "label": "Итоговый результат",
                    "type": "string",
                    "required": True,
                    "description": "Итоговый документ и адресат: проект, отчет, предложения",
                },
                {
                    "name": "termination_event",
                    "label": "Завершение деятельности",
                    "type": "string",
                    "required": True,
                    "description": "Событие: представление результата, утверждение документа или решение руководства",
                },
                {
                    "name": "is_it_project",
                    "label": "ИТ-проект",
                    "type": "boolean",
                    "required": True,
                    "default": False,
                    "description": "Создается ли группа для решения вопросов ИС/ИТ (требуется виза ДИТ)",
                },
                {
                    "name": "control_officer",
                    "label": "Контроль исполнения",
                    "type": "string",
                    "required": False,
                    "default": "Контроль за исполнением настоящего распоряжения оставляю за собой",
                    "description": "Должностное лицо, контролирующее исполнение",
                },
            ],
        },
    ]

    results: List[TemplateModuleDTO] = []

    for cfg in configs:
        # Match using unicode NFC normalized substring
        sub = cfg["pattern"].strip("*").lower()
        sub_norm = unicodedata.normalize("NFC", sub)
        matched_file: Optional[Path] = None
        for f in materials_dir.iterdir():
            if not f.name.endswith(".docx"):
                continue
            if sub_norm in unicodedata.normalize("NFC", f.name).lower():
                matched_file = f
                break

        if not matched_file:
            logger.warning(f"No file matching pattern {cfg['pattern']} found in {materials_dir}")
            continue

        file_path = matched_file
        file_name = normalize_unicode(file_path.name)
        doc = docx.Document(file_path)

        # Extract text chunks from template
        text_lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        full_text = "\n".join(text_lines)

        chunk = ExtractedChunk(
            chapter=f"Модульный документ: {cfg['title']}",
            clause=cfg["module_code"],
            page_number=1,
            content=full_text,
            metadata={
                "module_code": cfg["module_code"],
                "doc_kind": cfg["doc_kind"],
                "reg_number": cfg["reg_number"],
            },
        )

        results.append(
            TemplateModuleDTO(
                module_code=cfg["module_code"],
                doc_kind=cfg["doc_kind"],
                title=cfg["title"],
                reg_number=cfg["reg_number"],
                version="1.0",
                file_name=file_name,
                fields_schema=cfg["fields"],
                default_rule_number=cfg["default_rule_number"],
                chunks=[chunk],
            )
        )

    logger.info(f"Loaded {len(results)} template modules with dynamic schemas.")
    return results

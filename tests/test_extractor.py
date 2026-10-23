"""Unit tests for regulatory extractor module."""

from pathlib import Path
import pytest

from src.config import settings
from src.core.extractor import (
    ApprovalRuleDTO,
    DefinedTermDTO,
    ExtractedDocument,
    TemplateModuleDTO,
    extract_approval_matrix_data,
    extract_defined_terms,
    extract_guidelines_document,
    extract_pdf_instruction,
    extract_template_modules,
)


def test_extract_pdf_instruction():
    """Verify PDF extraction produces 256 granular chunks with proper chapters and clauses."""
    pdf_files = list(settings.MATERIALS_DIR.glob("*.pdf"))
    assert len(pdf_files) >= 1, "PDF instruction file not found"

    doc = extract_pdf_instruction(pdf_files[0])
    assert doc.doc_code == "OD-184"
    assert doc.doc_type == "instruction"
    assert doc.version == "1.0"
    assert len(doc.chunks) >= 250

    # Verify no chunks contain the raw watermark text
    watermark = "УЧЕБНЫЙ ПРИМЕР ДЛЯ ИТ-СОРЕВНОВАНИЙ"
    for c in doc.chunks:
        assert watermark not in c.content
        assert len(c.content) > 10
        assert c.page_number >= 1

    # Verify key clauses exist
    clauses = {c.clause for c in doc.chunks}
    assert "1.1" in clauses
    assert "1.4" in clauses
    assert "10.6" in clauses
    assert "12.16" in clauses


def test_extract_defined_terms():
    """Verify canonical terms and abbreviations are correctly extracted."""
    pdf_files = list(settings.MATERIALS_DIR.glob("*.pdf"))
    doc = extract_pdf_instruction(pdf_files[0])
    terms = extract_defined_terms(doc)

    assert len(terms) >= 25
    canonical_set = {t.canonical for t in terms}

    expected_canonicals = ["ИИС ДО", "ДОУ", "ЭД", "ЭКД", "ПД", "РК", "ЭП", "РБД", "ЛНА", "ДСП", "РО", "СП", "ЦА"]
    for exp in expected_canonicals:
        assert exp in canonical_set, f"Expected canonical term '{exp}' not found in glossary"

    # Verify fields
    for t in terms:
        assert len(t.canonical) > 0
        assert len(t.expansion) > 0
        assert t.source_doc_code == "OD-184"
        assert t.page_number is not None and t.page_number >= 1


def test_extract_guidelines_document():
    """Verify methodological guidelines extraction produces structured chunks."""
    guide_files = [f for f in settings.MATERIALS_DIR.iterdir() if "методические" in f.name.lower() and f.suffix == ".docx"]
    assert len(guide_files) >= 1, "Guidelines file not found"

    doc = extract_guidelines_document(guide_files[0])
    assert doc.doc_code == "METHOD-GUIDELINES"
    assert len(doc.chunks) >= 20

    clauses = {c.clause for c in doc.chunks}
    assert "1.1" in clauses
    assert "2.3" in clauses  # note field clause
    assert "3.3" in clauses  # cleanup instructions
    assert "4.2" in clauses  # approval sequence


def test_extract_approval_matrix_data():
    """Verify approval matrix parsing produces 13 rules with correct branches."""
    matrix_files = [f for f in settings.MATERIALS_DIR.iterdir() if "матрица" in f.name.lower() and f.suffix == ".docx"]
    assert len(matrix_files) >= 1, "Matrix file not found"

    doc, rules = extract_approval_matrix_data(matrix_files[0])
    assert doc.doc_code == "APPROVAL-MATRIX"
    assert len(rules) == 13

    # Rule 1: Weekend orders (Legal, DOU, HR)
    r1 = next(r for r in rules if r.rule_number == 1)
    assert r1.is_modular is True
    assert r1.requires_legal is True
    assert r1.requires_dou is True
    assert r1.requires_hr is True

    # Rule 3: Property transfer with Infosec access change
    r3 = next(r for r in rules if r.rule_number == 3)
    assert r3.requires_infosec == "yes"

    # Rule 4: IT systems (Infosec + IT)
    r4 = next(r for r in rules if r.rule_number == 4)
    assert r4.requires_infosec == "yes"
    assert r4.requires_it == "yes"

    # Rule 8: IT workgroups (IT yes)
    r8 = next(r for r in rules if r.rule_number == 8)
    assert r8.requires_it == "yes"

    # Rule 13: Letters by regional branches
    r13 = next(r for r in rules if r.rule_number == 13)
    assert r13.requires_regional == "yes"


def test_extract_template_modules():
    """Verify 7 modular templates with dynamic field schemas."""
    templates = extract_template_modules(settings.MATERIALS_DIR)
    assert len(templates) == 7

    module_codes = {t.module_code for t in templates}
    expected_codes = {
        "MOD-ORDER-IS",
        "MOD-ORDER-DOU",
        "MOD-ORDER-PROP",
        "MOD-ORDER-LNA",
        "MOD-DISP-AUDIT",
        "MOD-DISP-PROJECT",
        "MOD-DISP-WORKGROUP",
    }
    assert module_codes == expected_codes

    for tm in templates:
        assert tm.doc_kind in ("Приказ", "Распоряжение")
        assert len(tm.fields_schema) >= 5
        # Verify schema field items
        for f in tm.fields_schema:
            assert "name" in f
            assert "label" in f
            assert "type" in f
            assert "required" in f

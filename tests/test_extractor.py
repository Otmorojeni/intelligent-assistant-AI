"""Unit tests for regulatory extractor module."""

from pathlib import Path
import unittest

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


class TestExtractorUnit(unittest.TestCase):
    """Unit tests for regulatory extractor parsing of PDF, Word, terms, and templates."""

    def test_extract_pdf_instruction(self):
        """Verify PDF extraction produces 256 granular chunks with proper chapters and clauses."""
        pdf_files = list(settings.MATERIALS_DIR.glob("*.pdf"))
        self.assertGreaterEqual(len(pdf_files), 1, "PDF instruction file not found")

        doc = extract_pdf_instruction(pdf_files[0])
        self.assertEqual(doc.doc_code, "OD-184")
        self.assertEqual(doc.doc_type, "instruction")
        self.assertEqual(doc.version, "1.0")
        self.assertEqual(len(doc.chunks), 256)

        # Verify no chunks contain the raw watermark text
        watermark = "УЧЕБНЫЙ ПРИМЕР ДЛЯ ИТ-СОРЕВНОВАНИЙ"
        for c in doc.chunks:
            self.assertNotIn(watermark, c.content)
            self.assertGreater(len(c.content), 10)
            self.assertGreaterEqual(c.page_number, 1)

        # Verify key clauses exist
        clauses = {c.clause for c in doc.chunks}
        self.assertIn("1.1", clauses)
        self.assertIn("1.4", clauses)
        self.assertIn("4.1.3", clauses)
        self.assertIn("10.6", clauses)
        self.assertIn("12.16", clauses)

        # Verify chapter-clause alignment (no off-by-one chapter bleeding)
        for c in doc.chunks:
            if "." in c.clause:
                major = c.clause.split(".")[0]
                self.assertIn(
                    f"Глава {major}.",
                    c.chapter,
                    f"Clause {c.clause} is misattributed to chapter: {c.chapter}",
                )

        # Verify title chunk has title chapter
        titul_chunk = next(c for c in doc.chunks if c.clause == "Титул")
        self.assertEqual(titul_chunk.chapter, "Титульный лист и общие сведения")

    def test_extract_defined_terms(self):
        """Verify canonical terms and abbreviations are correctly extracted."""
        pdf_files = list(settings.MATERIALS_DIR.glob("*.pdf"))
        doc = extract_pdf_instruction(pdf_files[0])
        terms = extract_defined_terms(doc)

        self.assertGreaterEqual(len(terms), 25)
        canonical_set = {t.canonical for t in terms}

        expected_canonicals = [
            "ИИС ДО", "ДОУ", "ЭД", "ЭКД", "ПД", "РК", "ЭП", "РБД",
            "ЛНА", "ДСП", "РО", "СП", "ЦА", "СЭД",
        ]
        for exp in expected_canonicals:
            self.assertIn(exp, canonical_set, f"Expected canonical term '{exp}' not found in glossary")

        # Verify field hygiene
        for t in terms:
            self.assertGreater(len(t.canonical), 0)
            self.assertGreater(len(t.expansion), 0)
            self.assertIsNotNone(t.page_number)
            self.assertGreaterEqual(t.page_number, 1)

    def test_extract_guidelines_document(self):
        """Verify methodological guidelines extraction produces structured chunks with full 4.2 text."""
        guide_files = [f for f in settings.MATERIALS_DIR.iterdir() if "методические" in f.name.lower() and f.suffix == ".docx"]
        self.assertGreaterEqual(len(guide_files), 1, "Guidelines file not found")

        doc = extract_guidelines_document(guide_files[0])
        self.assertEqual(doc.doc_code, "METHOD-GUIDELINES")
        self.assertEqual(len(doc.chunks), 22)

        clauses = {c.clause for c in doc.chunks}
        self.assertIn("1.1", clauses)
        self.assertIn("2.3", clauses)
        self.assertIn("3.3", clauses)
        self.assertIn("4.2", clauses)
        self.assertIn("4.3", clauses)

        # Verify clause 4.2 contains all sequential approval steps and no fake sections exist
        c_42 = next(c for c in doc.chunks if c.clause == "4.2")
        self.assertIn("ответственный исполнитель", c_42.content)
        self.assertIn("корректор", c_42.content)
        self.assertIn("Департамент ДОУ", c_42.content)
        self.assertEqual(c_42.chapter, "Раздел 4. Проверка, визирование и лингвистическая экспертиза")

        # Verify no fake section chapters
        for c in doc.chunks:
            self.assertNotIn("ответственный исполнитель", c.chapter)
            self.assertNotIn("корректор", c.chapter)

    def test_extract_approval_matrix_data(self):
        """Verify approval matrix parsing produces 13 rules with correct branches."""
        matrix_files = [f for f in settings.MATERIALS_DIR.iterdir() if "матрица" in f.name.lower() and f.suffix == ".docx"]
        self.assertGreaterEqual(len(matrix_files), 1, "Matrix file not found")

        doc, rules = extract_approval_matrix_data(matrix_files[0])
        self.assertEqual(doc.doc_code, "APPROVAL-MATRIX")
        self.assertEqual(len(rules), 13)

        # Rule 1: Weekend orders (Legal, DOU, HR)
        r1 = next(r for r in rules if r.rule_number == 1)
        self.assertTrue(r1.is_modular)
        self.assertTrue(r1.requires_legal)
        self.assertTrue(r1.requires_dou)
        self.assertTrue(r1.requires_hr)

        # Rule 3: Property transfer with Infosec access change
        r3 = next(r for r in rules if r.rule_number == 3)
        self.assertEqual(r3.requires_infosec, "yes")

        # Rule 4: IT systems (Infosec + IT)
        r4 = next(r for r in rules if r.rule_number == 4)
        self.assertEqual(r4.requires_infosec, "yes")
        self.assertEqual(r4.requires_it, "yes")

        # Rule 8: IT workgroups (IT yes)
        r8 = next(r for r in rules if r.rule_number == 8)
        self.assertEqual(r8.requires_it, "yes")

        # Rule 13: Letters by regional branches
        r13 = next(r for r in rules if r.rule_number == 13)
        self.assertEqual(r13.requires_regional, "yes")

    def test_extract_template_modules(self):
        """Verify 7 modular templates with dynamic field schemas and valid file metadata."""
        templates = extract_template_modules(settings.MATERIALS_DIR)
        self.assertEqual(len(templates), 7)

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
        self.assertEqual(module_codes, expected_codes)

        for tm in templates:
            self.assertIn(tm.doc_kind, ("Приказ", "Распоряжение"))
            self.assertGreaterEqual(len(tm.fields_schema), 5)
            self.assertGreater(tm.file_size, 0, f"Template {tm.module_code} has zero file_size")
            self.assertGreater(len(tm.sha256), 32, f"Template {tm.module_code} has invalid sha256")
            for f in tm.fields_schema:
                self.assertIn("name", f)
                self.assertIn("label", f)
                self.assertIn("type", f)
                self.assertIn("required", f)


if __name__ == "__main__":
    unittest.main()

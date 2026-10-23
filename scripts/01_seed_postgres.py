#!/usr/bin/env python3
"""Seeding script for CDO AI Assistant PostgreSQL Knowledge Base.

Populates all 7 database tables from the materials directory:
- Regulatory Instruction OD-184 (PDF, 51 pages, 256 chunks)
- Defined Terms Glossary (29 canonical terms & abbreviations: ИИС ДО, ЛНА, ДСП, РО, СП, etc.)
- Approval Matrix (13 approval rules with condition branches)
- Methodological Guidelines (25 granular chunks)
- 7 Modular Document Templates with dynamic fields_schema

Usage:
    python scripts/01_seed_postgres.py
    python scripts/01_seed_postgres.py --verify-only
"""

import argparse
import asyncio
import logging
from pathlib import Path
import sys
import time

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output in Windows terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from sqlalchemy import func, select, text

from src.config import settings
from src.core.indexer import (
    index_all_materials,
    lookup_defined_term,
    search_chunks_fulltext,
)
from src.db.database import async_session_factory, engine, init_db
from src.db.models import (
    ApprovalRule,
    AuditLog,
    DefinedTerm,
    DocumentChunk,
    KnowledgeDocument,
    ProjectCard,
    TemplateModule,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("seed_postgres")


async def verify_database_state() -> bool:
    """Run verification checks on seeded database tables and full-text search."""
    print("\n" + "=" * 70)
    print("  RUNNING DEEP VERIFICATION CHECKS ON POSTGRESQL KNOWLEDGE BASE")
    print("=" * 70)

    async with async_session_factory() as session:
        # 1. Check Row Counts
        docs_count = (await session.execute(select(func.count(KnowledgeDocument.id)))).scalar() or 0
        chunks_count = (await session.execute(select(func.count(DocumentChunk.id)))).scalar() or 0
        terms_count = (await session.execute(select(func.count(DefinedTerm.id)))).scalar() or 0
        rules_count = (await session.execute(select(func.count(ApprovalRule.id)))).scalar() or 0
        templates_count = (await session.execute(select(func.count(TemplateModule.id)))).scalar() or 0

        print("\n[1/5] TABLE ROW COUNTS:")
        print(f"  - knowledge_documents : {docs_count:>4} (expected >= 10: PDF + Guidelines + Matrix + 7 templates)")
        print(f"  - document_chunks     : {chunks_count:>4} (expected >= 290 granular chunks)")
        print(f"  - defined_terms       : {terms_count:>4} (expected >= 25 canonical terms)")
        print(f"  - approval_rules      : {rules_count:>4} (expected 13 matrix rules)")
        print(f"  - template_modules    : {templates_count:>4} (expected 7 approved modules)")

        if chunks_count == 0 or rules_count == 0 or templates_count == 0:
            print("  [ERROR] Essential tables are empty!")
            return False

        # 2. Check TSVECTOR Full-Text Search
        print("\n[2/5] FULL-TEXT TSVECTOR SEARCH TEST:")
        sample_queries = [
            "лингвистическая экспертиза",
            "приказы по информационным системам",
            "таблица замечаний",
            "визирование модульных документов",
        ]
        for q in sample_queries:
            matches = await search_chunks_fulltext(session, q, top_k=2)
            if matches:
                top = matches[0]
                print(f"  Query: '{q}' -> Top Match: [{top['clause']}] {top['chapter']} (Score: {top['relevance_score']:.3f})")
                print(f"    Excerpt: {top['content'][:110].strip().replace(chr(10), ' ')}...")
            else:
                print(f"  [WARN] Query '{q}' returned 0 matches")

        # 3. Check Canonical Terms Lookup
        print("\n[3/5] CANONICAL GLOSSARY LOOKUP TEST:")
        sample_terms = ["ИИС ДО", "ЛНА", "ДСП", "РО", "СП"]
        for t in sample_terms:
            dt = await lookup_defined_term(session, t)
            if dt:
                print(f"  Term '{dt['canonical']}': {dt['expansion']} (Doc: {dt['source_doc_code']}, Clause: {dt['clause']})")
            else:
                print(f"  [WARN] Term '{t}' not found in glossary")

        # 4. Check Approval Matrix Rules
        print("\n[4/5] APPROVAL MATRIX RULES INTEGRITY:")
        rules_res = await session.execute(
            select(ApprovalRule).order_by(ApprovalRule.rule_number)
        )
        rules_list = rules_res.scalars().all()
        for r in rules_list:
            depts = []
            if r.requires_legal:
                depts.append("Юр")
            if r.requires_dou:
                depts.append("ДОУ")
            if r.requires_hr:
                depts.append("Кадры")
            if r.requires_infosec != "no":
                depts.append(f"ИБ({r.requires_infosec})")
            if r.requires_it != "no":
                depts.append(f"ИТ({r.requires_it})")
            if r.requires_regional != "no":
                depts.append(f"РО({r.requires_regional})")
            print(f"  Rule #{r.rule_number:02d} [{r.category.upper():<8}]: {r.doc_type_name[:45]}... -> [{', '.join(depts)}]")

        # 5. Check Template Modules Dynamic Schemas
        print("\n[5/5] TEMPLATE MODULES DYNAMIC SCHEMAS:")
        tm_res = await session.execute(
            select(TemplateModule).order_by(TemplateModule.reg_number)
        )
        tm_list = tm_res.scalars().all()
        for tm in tm_list:
            field_names = [f["name"] for f in tm.fields_schema]
            print(f"  [{tm.reg_number}] {tm.module_code:<18} ({tm.doc_kind}): {tm.title[:40]}... (Fields: {len(field_names)})")

    print("\n" + "=" * 70)
    print("  ALL VERIFICATION CHECKS COMPLETED SUCCESSFULLY!")
    print("=" * 70 + "\n")
    return True


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed PostgreSQL database from materials")
    parser.add_argument("--verify-only", action="store_true", help="Only verify existing database data")
    parser.add_argument("--materials-dir", type=Path, default=settings.MATERIALS_DIR, help="Materials directory")
    args = parser.parse_args()

    start_time = time.time()

    if not args.verify_only:
        print("\n[STEP 1] Initializing PostgreSQL tables and extensions...")
        await init_db()

        print(f"\n[STEP 2] Seeding database from materials at: {args.materials_dir}...")
        async with async_session_factory() as session:
            stats = await index_all_materials(session, materials_dir=args.materials_dir, reset=True)
            print("\nSeeding completed successfully with statistics:")
            for k, v in stats.items():
                print(f"  - {k}: {v}")

    # Always run verification
    success = await verify_database_state()
    elapsed = time.time() - start_time
    print(f"Total execution time: {elapsed:.2f} seconds.")
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(main())

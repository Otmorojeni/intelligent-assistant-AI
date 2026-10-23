"""Unified test runner and comprehensive test suite for CDO AI Assistant knowledge base."""

import asyncio
from pathlib import Path
import sys
import unittest

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 output
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Import the authoritative test cases
from tests.test_approval_router import TestApprovalRouter
from tests.test_extractor import TestExtractorUnit
from tests.test_indexer_integration import TestIndexerIntegration
from tests.test_pipeline import TestPipeline
from tests.test_retriever import TestRetriever


def suite() -> unittest.TestSuite:
    """Create unified test suite containing all unit and integration tests."""
    s = unittest.TestSuite()
    loader = unittest.TestLoader()
    s.addTests(loader.loadTestsFromTestCase(TestExtractorUnit))
    s.addTests(loader.loadTestsFromTestCase(TestIndexerIntegration))
    s.addTests(loader.loadTestsFromTestCase(TestRetriever))
    s.addTests(loader.loadTestsFromTestCase(TestPipeline))
    s.addTests(loader.loadTestsFromTestCase(TestApprovalRouter))
    return s


def load_tests(loader, standard_tests, pattern):
    """Prevent double-execution when tests are auto-discovered from test_extractor and test_indexer_integration."""
    return unittest.TestSuite()


if __name__ == "__main__":
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite())
    sys.exit(0 if result.wasSuccessful() else 1)

"""Tests package initialization.

Configures event loop for Windows (psycopg async compatibility) and filters deprecation warnings.
"""

import asyncio
import sys
import warnings

# psycopg async requires SelectorEventLoop on Windows
if sys.platform == "win32":
    warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*WindowsSelectorEventLoopPolicy.*")
    warnings.filterwarnings("ignore", category=DeprecationWarning, message=".*set_event_loop_policy.*")
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

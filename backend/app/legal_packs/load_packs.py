
"""Standalone entry point: ``python -m app.legal_packs.load_packs`` (spec/backend.md B5).

Loading legal packs is split from the FastAPI ``lifespan`` hook on purpose: a
fresh environment may start the API container before ``alembic upgrade head``
has run, and a DB write against an unmigrated schema should not crash process
startup. ``app/main.py`` still calls :func:`load_all_packs` from ``lifespan``,
but wrapped in a try/except that only logs a warning (see the module docstring
there) -- this script is the reliable, explicit way to (re)load packs as part of
the documented startup sequence, analogous to ``python -m app.seed_demo``.
"""

from __future__ import annotations

import logging
import sys

from app.db import session_scope
from app.legal_packs.loader import load_all_packs

logger = logging.getLogger("app.legal_packs.load_packs")


def main(argv: list[str] | None = None) -> int:
    """Load every packaged legal pack asset. Safe to run repeatedly."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    del argv  # no command-line options
    with session_scope() as db:
        loaded = load_all_packs(db)

    print("Loaded legal packs:")
    for pack in loaded:
        print(
            f"  {pack.version:<16} case_type={pack.case_type.value:<24} "
            f"coverage={pack.coverage.value:<12} checks={pack.check_count} "
            f"legal_references={pack.legal_reference_count}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())

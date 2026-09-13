"""Versioned legal-pack JSON assets and their idempotent loader (spec/backend.md B5).

Packs are static files shipped with the backend, not something the model or a
request can influence. ``loader.py`` upserts each asset's ``LegalPack``,
``LegalReference`` and ``Check`` rows; nothing here accepts check-level legal
fields from any source other than the committed JSON asset.
"""

from __future__ import annotations

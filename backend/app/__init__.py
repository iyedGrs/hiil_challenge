"""Dispute preparation backend package (spec/backend.md B2, spec/local-dev.md L2).

One codebase serves the API process (``app.main:app``) and the worker process
(``python -m app.worker``). Nothing in this package performs AI provider calls
during the foundation slice.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"

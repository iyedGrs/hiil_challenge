"""HTTP routers for the canonical contract (spec/backend.md B9).

FastAPI owns the ``/api`` prefix; the Vite proxy must not strip it
(spec/local-dev.md L1). Every route that touches case data performs server-side
authorization (B8); the foundation slice ships config, auth and health.
"""

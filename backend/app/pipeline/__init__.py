"""Analysis and export pipeline (spec/backend.md B6, B7, B10).

Split by responsibility so each boundary the spec draws is enforced in one file:

* :mod:`app.pipeline.facts` -- Stage 1 extraction, caching and the source-quote
  validation that decides whether a fact may support a published judgment (B7).
* :mod:`app.pipeline.subjects` -- backend-owned stable subject identity (B6, B7).
* :mod:`app.pipeline.reconcile` -- deterministic ``Decimal`` arithmetic. The only
  place a monetary conclusion is ever produced (B7).
* :mod:`app.pipeline.publish` -- finding identity, deltas, coverage and the atomic
  publication of a run (B7).
* :mod:`app.pipeline.analysis` -- the worker handler that orchestrates the above.
* :mod:`app.pipeline.export` -- the reviewer package (B10).
"""

# Legacy Dashboard Tests

These files belong to the older V3/V4 interactive dashboard service stack. They
can start local web servers, sleep indefinitely, and depend on legacy service
symbols such as `MTAIService`.

They are intentionally excluded from the default `python -m pytest` suite for
the demo-first `xm-gold-ai-trader` scaffold. Current safety and research
verification lives in the top-level `tests/` files outside this directory.

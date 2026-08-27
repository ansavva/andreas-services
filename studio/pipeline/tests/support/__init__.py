"""Harnesses the suite is built on. No tests here — pytest collects `test_*`.

`fake_api.py` answers `adapters.api.request` out of memory, with real uuids,
real 409s on a duplicate slug and real `rev` compare-and-swap. It is the seam
the whole unit suite hangs off, which is why it is 1300 lines and why it is
named as infrastructure rather than sitting among the test modules.
"""

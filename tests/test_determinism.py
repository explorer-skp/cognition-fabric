"""Determinism is sacred (CLAUDE.md): the seeded smoke run must be byte-identical across runs.

The live demo depends on this, and "our chaos is replayable" is a defence point. This test is
non-negotiable and grows as more of the fabric becomes observable.
"""

from __future__ import annotations

from demo.demo_smoke import _format, run_smoke


def test_smoke_metrics_identical_across_runs():
    run_a = run_smoke()
    run_b = run_smoke()
    assert run_a == run_b


def test_smoke_output_byte_identical_across_runs():
    text_a = "\n".join(_format(r) for r in run_smoke())
    text_b = "\n".join(_format(r) for r in run_smoke())
    assert text_a == text_b


def test_taskgen_stream_identical_across_runs():
    from world.taskgen import generate

    a = generate(seed=12345, n=20)
    b = generate(seed=12345, n=20)
    assert a == b
    # A different seed must produce a different stream (the seed actually matters).
    assert generate(seed=999, n=20) != a

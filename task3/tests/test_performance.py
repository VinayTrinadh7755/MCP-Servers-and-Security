from __future__ import annotations

import time

from task3.scripts.benchmark import run_benchmark
from task3.gateway.redactor import MAX_PATTERN_LEN


def test_benchmark_reports_medians_and_plausible_metrics() -> None:
    result = run_benchmark(runs=5, throughput_bytes=256 * 1024)
    assert result.runs == 5
    assert result.baseline_ttft_ms >= 0
    assert result.guarded_ttft_ms >= result.baseline_ttft_ms
    assert result.frames_to_first_guarded_output > 1
    assert result.throughput_mib_s > 0.1
    assert result.normal_carry_limit > 0
    assert result.measured_peak_buffer_chars <= MAX_PATTERN_LEN * 2


def test_pattern_like_work_scales_without_quadratic_blowup() -> None:
    small_started = time.perf_counter()
    run_benchmark(runs=5, throughput_bytes=128 * 1024)
    small_elapsed = time.perf_counter() - small_started

    large_started = time.perf_counter()
    run_benchmark(runs=5, throughput_bytes=256 * 1024)
    large_elapsed = time.perf_counter() - large_started

    # Doubling work should remain comfortably below a quadratic 4x increase.
    # The additive TTFT samples make the ratio smaller, so 3.5x is intentionally
    # generous across slow CI and developer machines.
    assert large_elapsed < small_elapsed * 3.5

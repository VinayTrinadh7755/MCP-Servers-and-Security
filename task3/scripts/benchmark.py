"""Reproducible offline latency and throughput benchmark for Task 3."""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path


# This file is intentionally runnable as `python task3/scripts/benchmark.py`
# from a clean checkout without requiring an editable package installation.
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from task3.gateway.redactor import MAX_PATTERN_LEN, StreamRedactor  # noqa: E402


MIB = 1024 * 1024


@dataclass(frozen=True)
class BenchmarkResult:
    runs: int
    baseline_ttft_ms: float
    guarded_ttft_ms: float
    ttft_delta_ms: float
    frames_to_first_guarded_output: int
    throughput_mib_s: float
    normal_carry_limit: int
    measured_peak_buffer_chars: int


def _ttft_once(chunks: list[str], guarded: bool) -> tuple[float, int]:
    started = time.perf_counter_ns()
    if not guarded:
        # Equivalent pass-through work: inspect the first delta and emit it.
        _ = chunks[0]
        return (time.perf_counter_ns() - started) / 1_000_000, 1

    redactor = StreamRedactor()
    for index, chunk in enumerate(chunks, start=1):
        if redactor.feed(chunk):
            return (time.perf_counter_ns() - started) / 1_000_000, index
    redactor.flush()
    return (time.perf_counter_ns() - started) / 1_000_000, len(chunks)


def _throughput_once(size_bytes: int, chunk_size: int) -> float:
    # Pattern-like near matches exercise regex work without becoming valid PII.
    unit = "1234x-name@example-clean "
    text = (unit * (size_bytes // len(unit) + 1))[:size_bytes]
    redactor = StreamRedactor()
    started = time.perf_counter()
    emitted = 0
    for offset in range(0, len(text), chunk_size):
        emitted += len(redactor.feed(text[offset : offset + chunk_size]))
    emitted += len(redactor.flush())
    elapsed = time.perf_counter() - started
    if emitted != len(text):
        raise AssertionError("benchmark clean input changed length")
    return (len(text) / MIB) / elapsed


def _measure_peak_buffer(size_bytes: int = MIB, chunk_size: int = 1024) -> int:
    redactor = StreamRedactor()
    peak = 0
    remaining = size_bytes
    while remaining:
        size = min(chunk_size, remaining)
        redactor.feed("x" * size)
        peak = max(peak, redactor.buffered_characters)
        remaining -= size
    redactor.flush()
    return peak


def run_benchmark(
    *, runs: int = 7, throughput_bytes: int = 512 * 1024, chunk_size: int = 32
) -> BenchmarkResult:
    if runs < 5:
        raise ValueError("at least five runs are required for a meaningful median")
    fixture = "clean-stream-data-" * 80
    chunks = [fixture[index : index + chunk_size] for index in range(0, len(fixture), chunk_size)]

    baseline_samples: list[float] = []
    guarded_samples: list[float] = []
    guarded_frames: list[int] = []
    throughput_samples: list[float] = []
    for _ in range(runs):
        baseline, _ = _ttft_once(chunks, guarded=False)
        guarded, frames = _ttft_once(chunks, guarded=True)
        baseline_samples.append(baseline)
        guarded_samples.append(guarded)
        guarded_frames.append(frames)
        throughput_samples.append(_throughput_once(throughput_bytes, 4096))

    baseline_median = statistics.median(baseline_samples)
    guarded_median = statistics.median(guarded_samples)
    return BenchmarkResult(
        runs=runs,
        baseline_ttft_ms=baseline_median,
        guarded_ttft_ms=guarded_median,
        ttft_delta_ms=guarded_median - baseline_median,
        frames_to_first_guarded_output=int(statistics.median(guarded_frames)),
        throughput_mib_s=statistics.median(throughput_samples),
        normal_carry_limit=MAX_PATTERN_LEN - 1,
        measured_peak_buffer_chars=_measure_peak_buffer(),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=7)
    parser.add_argument("--throughput-kib", type=int, default=1024)
    args = parser.parse_args()
    result = run_benchmark(runs=args.runs, throughput_bytes=args.throughput_kib * 1024)
    print(f"runs={result.runs} statistic=median")
    print(f"baseline_ttft_ms={result.baseline_ttft_ms:.4f}")
    print(f"guarded_ttft_ms={result.guarded_ttft_ms:.4f}")
    print(f"compute_ttft_delta_ms={result.ttft_delta_ms:.4f}")
    print(f"frames_to_first_guarded_output={result.frames_to_first_guarded_output}")
    print(f"normal_carry_limit_chars={result.normal_carry_limit}")
    print(f"measured_peak_buffer_chars_1mib={result.measured_peak_buffer_chars}")
    print(f"regex_throughput_mib_s={result.throughput_mib_s:.2f}")
    print(
        "modeled_content_delay=frames_to_first_guarded_output_minus_one "
        "times upstream_frame_interval"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

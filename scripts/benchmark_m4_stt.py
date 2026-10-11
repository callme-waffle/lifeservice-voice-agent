"""Repeatable M4 Korean STT measurement on an otherwise idle GPU host.

Run one model per process to avoid carrying VRAM across candidates.
The sample directory contains files from deeplyinc/Korean-Read-Speech-Corpus.
"""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import threading
import time
import unicodedata
import wave
from pathlib import Path


SAMPLE_NAMES = (
    "sub100100a00000",
    "sub100100a00001",
    "sub100100a00002",
)


def gpu_memory_mib() -> int:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip().splitlines()[0].strip())


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return "".join(char for char in text if char.isalnum()).casefold()


def edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for row, char in enumerate(left, 1):
        current = [row]
        for column, other in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (char != other),
                )
            )
        previous = current
    return previous[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--model", choices=("small", "medium"), required=True)
    parser.add_argument("--compute-type", default="int8")
    args = parser.parse_args()

    from faster_whisper import WhisperModel

    metadata = json.loads(
        (args.samples / "Korean_Read_Speech_Corpus_sample.json").read_text()
    )
    samples = []
    for name in SAMPLE_NAMES:
        path = args.samples / f"{name}.wav"
        with wave.open(str(path), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
            rate = audio.getframerate()
            channels = audio.getnchannels()
        samples.append(
            {
                "name": name,
                "path": str(path),
                "reference": metadata["AirbnbStudio"][name]["text"],
                "duration_s": duration,
                "sample_rate_hz": rate,
                "channels": channels,
            }
        )

    baseline = gpu_memory_mib()
    readings = [baseline]
    stop = threading.Event()

    def poll_memory() -> None:
        while not stop.wait(0.1):
            try:
                readings.append(gpu_memory_mib())
            except (OSError, ValueError, subprocess.CalledProcessError):
                pass

    poller = threading.Thread(target=poll_memory, daemon=True)
    poller.start()
    try:
        start = time.perf_counter()
        model = WhisperModel(
            args.model, device="cuda", compute_type=args.compute_type
        )
        load_s = time.perf_counter() - start

        # Warm the same path before timed runs; loading/download time is separate.
        start = time.perf_counter()
        list(model.transcribe(samples[0]["path"], language="ko", beam_size=5)[0])
        warmup_s = time.perf_counter() - start

        total_edits = 0
        total_characters = 0
        for sample in samples:
            start = time.perf_counter()
            segments, _ = model.transcribe(
                sample["path"], language="ko", beam_size=5
            )
            hypothesis = " ".join(segment.text.strip() for segment in segments)
            sample["latency_s"] = round(time.perf_counter() - start, 4)
            sample["hypothesis"] = hypothesis
            reference = normalized(sample["reference"])
            actual = normalized(hypothesis)
            sample["character_edits"] = edit_distance(reference, actual)
            sample["reference_characters"] = len(reference)
            total_edits += sample["character_edits"]
            total_characters += len(reference)
    finally:
        stop.set()
        poller.join(timeout=1)
        readings.append(gpu_memory_mib())

    print(
        json.dumps(
            {
                "model": args.model,
                "compute_type": args.compute_type,
                "device": "cuda",
                "beam_size": 5,
                "language": "ko",
                "model_load_s": round(load_s, 4),
                "warmup_s": round(warmup_s, 4),
                "process_peak_rss_mib": round(
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
                ),
                "gpu_baseline_mib": baseline,
                "gpu_peak_mib": max(readings),
                "gpu_peak_delta_mib": max(readings) - baseline,
                "character_error_rate": round(total_edits / total_characters, 4),
                "samples": samples,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

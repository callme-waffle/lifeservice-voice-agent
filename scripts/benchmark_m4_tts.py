"""Measure MeloTTS Korean on the M4 GPU host with fixed sentences."""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import threading
import time
import wave
from pathlib import Path


SENTENCES = (
    "안녕하세요. 무엇을 도와드릴까요?",
    "요청하신 결과를 확인했습니다. 자세한 내용은 화면에서 확인해 주세요.",
)


def gpu_memory_mib() -> int:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(result.stdout.strip().splitlines()[0].strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()
    if not 0.5 <= args.speed <= 2.0:
        parser.error("--speed must be between 0.5 and 2.0")
    args.output.mkdir(parents=True, exist_ok=True)

    from melo.api import TTS

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
        model = TTS(language="KR", device="cuda:0")
        load_s = time.perf_counter() - start
        speaker = model.hps.data.spk2id["KR"]

        start = time.perf_counter()
        model.tts_to_file(SENTENCES[0], speaker, str(args.output / "warmup.wav"), speed=args.speed)
        warmup_s = time.perf_counter() - start

        samples = []
        for index, sentence in enumerate(SENTENCES):
            path = args.output / f"sentence-{index}.wav"
            start = time.perf_counter()
            model.tts_to_file(sentence, speaker, str(path), speed=args.speed)
            latency_s = time.perf_counter() - start
            with wave.open(str(path), "rb") as audio:
                audio_duration_s = audio.getnframes() / audio.getframerate()
                sample_rate_hz = audio.getframerate()
                channels = audio.getnchannels()
            samples.append(
                {
                    "text": sentence,
                    "path": str(path),
                    "latency_s": round(latency_s, 4),
                    "audio_duration_s": round(audio_duration_s, 4),
                    "real_time_factor": round(latency_s / audio_duration_s, 4),
                    "sample_rate_hz": sample_rate_hz,
                    "channels": channels,
                }
            )
    finally:
        stop.set()
        poller.join(timeout=1)
        readings.append(gpu_memory_mib())

    print(
        json.dumps(
            {
                "model": "myshell-ai/MeloTTS-Korean",
                "device": "cuda:0",
                "speaker": "KR",
                "speed": args.speed,
                "model_load_s": round(load_s, 4),
                "warmup_s": round(warmup_s, 4),
                "process_peak_rss_mib": round(
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1
                ),
                "gpu_baseline_mib": baseline,
                "gpu_peak_mib": max(readings),
                "gpu_peak_delta_mib": max(readings) - baseline,
                "samples": samples,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

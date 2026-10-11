"""Read-only NVIDIA GPU metrics for Prometheus without a DCGM dependency."""

from __future__ import annotations

import subprocess
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_error(404)
            return
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=3, check=True,
            )
            lines = []
            for index, row in enumerate(result.stdout.strip().splitlines()):
                utilization, used_mib, total_mib = (float(value.strip()) for value in row.split(","))
                lines.extend((
                    f'voice_gpu_utilization_percent{{gpu="{index}"}} {utilization}',
                    f'voice_gpu_memory_used_bytes{{gpu="{index}"}} {used_mib * 1048576}',
                    f'voice_gpu_memory_total_bytes{{gpu="{index}"}} {total_mib * 1048576}',
                ))
            if not lines:
                raise ValueError("no GPU detected")
        except (OSError, ValueError, subprocess.SubprocessError):
            self.send_error(503, "GPU metrics unavailable")
            return
        body = ("\n".join(lines) + "\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer((os.getenv("GPU_METRICS_BIND_HOST", "127.0.0.1"), 9400), Handler).serve_forever()

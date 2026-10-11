"""Content-free voice stage timing and OTLP tracing."""

from __future__ import annotations

from contextlib import contextmanager
from time import monotonic

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Histogram


STAGE_SECONDS = Histogram(
    "voice_stage_duration_seconds", "Voice processing stage duration", ["stage"],
    buckets=(.1, .25, .5, 1, 2, 5, 10, 20, 40, 80, 160),
)


def configure_tracing(endpoint: str | None, service_name: str) -> TracerProvider | None:
    if endpoint is None:
        return None
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    return provider


@contextmanager
def stage(name: str):
    started = monotonic()
    with trace.get_tracer("voice-agent").start_as_current_span(f"voice.{name}") as span:
        span.set_attribute("voice.stage", name)
        try:
            yield
        finally:
            STAGE_SECONDS.labels(stage=name).observe(monotonic() - started)

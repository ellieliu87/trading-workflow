"""
Arize Phoenix tracing setup for the trading workflow.

Instruments:
  - OpenAI Agents SDK spans (agent runs, tool calls, handoffs)
  - Raw OpenAI API calls

Usage:
    from tracing.phoenix_setup import setup_tracing, get_tracer
    setup_tracing()   # call once at startup
"""

from __future__ import annotations

import atexit
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def setup_tracing(
    project_name: str = "trading-workflow",
    host: Optional[str] = None,
    port: Optional[int] = None,
    launch_local: bool = True,
) -> None:
    """
    Configure Arize Phoenix + OpenTelemetry instrumentation.

    Args:
        project_name: Phoenix project label shown in the UI.
        host: Phoenix server host (default: $PHOENIX_HOST or 127.0.0.1).
        port: Phoenix server port (default: $PHOENIX_PORT or 6006).
        launch_local: If True, start an in-process Phoenix server (development).
                      Set False when pointing at a remote Phoenix instance.
    """
    host = host or os.getenv("PHOENIX_HOST", "127.0.0.1")
    port = int(port or os.getenv("PHOENIX_PORT", "6006"))
    endpoint = f"http://{host}:{port}/v1/traces"

    # ── 1. Launch local Phoenix (optional) ──────────────────────────────────
    if launch_local:
        try:
            import phoenix as px
            session = px.launch_app()
            logger.info("Arize Phoenix UI: %s", session.url)
            # Shut Phoenix down cleanly before Python exits so the SQLite
            # database lock is released before tempfile cleanup runs (Windows).
            atexit.register(px.close_app)
        except ImportError:
            logger.warning("arize-phoenix not installed – skipping local server launch.")
        except Exception as exc:
            logger.warning("Could not launch Phoenix: %s", exc)

    # ── 2. Register OTEL tracer provider ────────────────────────────────────
    try:
        from phoenix.otel import register

        tracer_provider = register(
            project_name=project_name,
            endpoint=endpoint,
        )
        logger.info("Phoenix tracer registered → %s (project=%s)", endpoint, project_name)
    except ImportError:
        logger.warning("phoenix.otel not available – using plain OTLP exporter.")
        tracer_provider = _build_otlp_provider(project_name, endpoint)

    # ── 3. Instrument OpenAI Agents SDK ─────────────────────────────────────
    try:
        from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor

        OpenAIAgentsInstrumentor().instrument(tracer_provider=tracer_provider)
        logger.info("OpenAI Agents SDK instrumented.")
    except ImportError:
        logger.warning(
            "openinference-instrumentation-openai-agents not installed. "
            "Agent-level spans will not appear in Phoenix."
        )

    # ── 4. Instrument raw OpenAI client calls ────────────────────────────────
    try:
        from openinference.instrumentation.openai import OpenAIInstrumentor

        OpenAIInstrumentor().instrument(tracer_provider=tracer_provider)
        logger.info("OpenAI API instrumented.")
    except ImportError:
        logger.warning(
            "openinference-instrumentation-openai not installed. "
            "Raw API spans will not appear in Phoenix."
        )


def _build_otlp_provider(project_name: str, endpoint: str):
    """Fallback: plain OTLP exporter without phoenix.otel helper."""
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource

    resource = Resource.create({"service.name": project_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def get_tracer(name: str = "trading-workflow"):
    """Return an OTEL tracer for manual spans."""
    from opentelemetry import trace

    return trace.get_tracer(name)

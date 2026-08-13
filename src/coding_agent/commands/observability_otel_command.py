"""The /observability-otel command: confirms the advanced (real OTel) tier
is active and points you at where to actually look.

Unlike /observability (the lightweight tier), the data here doesn't live
in this process - it's already been exported to a real backend (local
Docker Grafana, or your own Grafana Cloud stack). So this command's job
isn't to replicate a dashboard in text, just to say where to go look.
"""

from coding_agent.commands.base import SlashCommand
from coding_agent.optimizations.observability_otel import ObservabilityOtelStatus


class ObservabilityOtelCommand(SlashCommand):
    """Prints where this session's real traces/metrics/logs are going."""

    def __init__(self, status: ObservabilityOtelStatus | None) -> None:
        self._status = status

    @property
    def name(self) -> str:
        return "observability-otel"

    @property
    def description(self) -> str:
        return (
            "Show where this session's real OpenTelemetry traces/metrics/"
            "logs are being exported to."
        )

    def run(self) -> str:
        if self._status is None or not self._status.active:
            return (
                "--- Observability (OTel) ---\n"
                "Not active. Make sure OTEL_EXPORTER_OTLP_ENDPOINT is set "
                "(see optimizations/observability_stack.py for the local "
                "path, or AGENTS.md's Observability section for the cloud "
                "path), and you launched with --enable observability-otel."
            )

        lines = [
            "--- Observability (OTel) ---",
            "Status       : active - traces, metrics, and logs are exporting live",
            f"Endpoint     : {self._status.endpoint}",
        ]
        if self._status.grafana_url:
            lines.append(f"Open Grafana : {self._status.grafana_url}")
        else:
            lines.append("Open your own Grafana Cloud stack to view this session's data.")
        return "\n".join(lines)

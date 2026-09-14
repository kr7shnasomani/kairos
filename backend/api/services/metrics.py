"""
Kairos custom OTEL metrics instruments.
Instruments are created against the global MeterProvider set up in telemetry.py.
All are no-ops when MeterProvider is not configured (avoids import-order issues).
"""

from opentelemetry import metrics

_meter = metrics.get_meter("kairos", version="0.1.0")

briefs_delivered = _meter.create_counter(
    "kairos.briefs.delivered",
    description="Number of operator briefs delivered",
    unit="1",
)

governor_suppressed = _meter.create_counter(
    "kairos.governor.suppressed",
    description="Number of briefs suppressed by the EEMUA 191 push governor",
    unit="1",
)

ingestion_duration = _meter.create_histogram(
    "kairos.ingestion.duration",
    description="Document ingestion pipeline duration from upload to Temporal start",
    unit="s",
)

conflicts_open = _meter.create_up_down_counter(
    "kairos.conflicts.open",
    description="Number of open knowledge conflicts (dual-track governance)",
    unit="1",
)

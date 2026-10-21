"""Which answers are evaluated (Chapter 13).

A fixed share, chosen by trace ID before anything is known about the
answer, the comparison OpenTelemetry's TraceIdRatioBased sampler
makes. Every service that applies the rule picks the same answers,
and the sample is not biased toward errors and slow answers, as
Chapter 10's tail sampler is on purpose.
"""

LIMIT = (1 << 64) - 1


def selected(trace_id: int, rate: float) -> bool:
    if not 0 <= rate <= 1:
        raise ValueError(f"a rate lies between 0 and 1: {rate}")
    return trace_id & LIMIT < round(rate * (LIMIT + 1))

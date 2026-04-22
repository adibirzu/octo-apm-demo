"""Edge fuzzer — bursts forged-auth + oversized-payload requests at the
API Gateway to exercise WAF rules + rate limits + edge logging."""

from .fuzzer import EdgeFuzzer, FuzzStats

__all__ = ["EdgeFuzzer", "FuzzStats"]
__version__ = "1.0.0"

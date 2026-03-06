"""OCI Logging SDK + Splunk HEC log pusher."""

import json
import logging
import time
from datetime import datetime, timezone
from server.config import cfg

logger = logging.getLogger(__name__)


def push_log(level: str, message: str, **extra):
    """Push a structured log entry to OCI Logging and/or Splunk HEC."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        "service": cfg.app_name,
        "runtime": cfg.app_runtime,
        **extra,
    }

    # Always log to stdout (structured JSON)
    logger.log(getattr(logging, level, logging.INFO), json.dumps(entry))

    # OCI Logging SDK (if configured)
    if cfg.logging_configured:
        try:
            import oci
            signer = oci.auth.signers.get_resource_principals_signer()
            client = oci.loggingingestion.LoggingClient({}, signer=signer)
            client.put_logs(
                log_id=cfg.oci_log_id,
                put_logs_details=oci.loggingingestion.models.PutLogsDetails(
                    specversion="1.0",
                    log_entry_batches=[
                        oci.loggingingestion.models.LogEntryBatch(
                            entries=[
                                oci.loggingingestion.models.LogEntry(
                                    data=json.dumps(entry),
                                    id=f"{time.time_ns()}",
                                    time=entry["timestamp"],
                                )
                            ],
                            source=cfg.app_name,
                            type="mushop.application",
                        )
                    ],
                ),
            )
        except Exception:
            pass  # don't break the app if logging fails

    # Splunk HEC (if configured)
    if cfg.splunk_hec_url and cfg.splunk_hec_token:
        try:
            import httpx
            httpx.post(
                f"{cfg.splunk_hec_url}/services/collector/event",
                json={"event": entry, "sourcetype": "mushop:application"},
                headers={"Authorization": f"Splunk {cfg.splunk_hec_token}"},
                verify=False,
                timeout=5,
            )
        except Exception:
            pass

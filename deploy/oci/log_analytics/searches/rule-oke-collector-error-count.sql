-- ============================================================================
-- rule-oke-collector-error-count
-- Scheduled-search metric for OCI Kubernetes Monitoring collector errors.
-- ============================================================================
'Log Source' = 'Kubernetes Container Generic Logs'
and Namespace = 'oci-onm'
and (Error != null
     or 'Error Text' != null
     or 'Logging Analytics Error Type' != null
     or 'Logging Analytics Processing Errors' != null)
| stats count as OkeCollectorErrorEvents by Pod, Container

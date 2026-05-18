-- ============================================================================
-- rule-oke-onm-log-samples
-- Scheduled-search metric for OKE Log Analytics ingestion volume.
-- Alert in OCI Monitoring when this metric is absent or drops unexpectedly.
-- ============================================================================
('Log Source' in ('Kubernetes Container Generic Logs','Kubernetes TCP Connect Logs','SOC Application Logs')
 and 'Kubernetes Cluster Name' = 'octo-apm-demo-oke')
| stats count as OkeOnmLogSamples by 'Log Source', Namespace

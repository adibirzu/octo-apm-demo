-- ============================================================================
-- oke-onm-ingestion-health
-- Health view for OCI Kubernetes Monitoring ingestion. A healthy emdemo OKE
-- cluster should show container, tcpconnect, and ONM collector records.
-- ============================================================================
('Log Source' in ('Kubernetes Container Generic Logs','Kubernetes TCP Connect Logs','SOC Application Logs')
 and 'Kubernetes Cluster Name' = 'octo-apm-demo-oke')
| stats count as Records,
        distinctcount('Trace ID') as Traces,
        distinctcount(Pod) as Pods,
        values(Container) as Containers
  by 'Log Source', 'Kubernetes Cluster Name', Namespace
| sort -Records

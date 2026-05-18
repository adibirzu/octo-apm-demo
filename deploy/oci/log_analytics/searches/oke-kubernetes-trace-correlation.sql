-- ============================================================================
-- oke-kubernetes-trace-correlation
-- Confirms OKE app stdout records are landing on the reusable SOC Application
-- Logs source with trace/span/service fields promoted by the existing parser.
-- ============================================================================
('Log Source' = 'SOC Application Logs'
    and 'Kubernetes Cluster Name' = 'octo-apm-demo-oke'
    and 'Service Namespace' = 'octo')
or ('Log Source' = 'Kubernetes Container Generic Logs'
    and 'Kubernetes Cluster Name' = 'octo-apm-demo-oke'
    and Namespace in ('octo-drone-shop','enterprise-crm'))
| stats count as Records,
        distinctcount('Trace ID') as Traces,
        distinctcount('Span ID') as Spans,
        values(Pod) as Pods,
        values('Log Source') as 'Log Sources'
  by 'Kubernetes Cluster Name', Namespace, 'Service Name', 'Service Namespace'
| sort -Records

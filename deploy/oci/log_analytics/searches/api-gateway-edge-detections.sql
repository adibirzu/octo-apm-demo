-- ============================================================================
-- api-gateway-edge-detections
-- OCI API Gateway route-policy, auth, quota, and backend decisions correlated
-- with attack-lab trace ids.
-- Parameters: :attack_id optional, :trace_id optional.
-- ============================================================================
('API Gateway Request ID' != null)
| where (:attack_id = null or 'Attack ID' = :attack_id)
| where (:trace_id = null or 'Trace ID' = :trace_id)
| stats count as Events,
        min(Time) as 'First Seen',
        max(Time) as 'Last Seen',
        values('API Gateway Name') as Gateways,
        values('API Gateway Scope') as Scopes,
        values('API Gateway Deployment ID') as Deployments,
        values('API Gateway Route') as Routes,
        values('API Gateway Policy Decision') as Decisions,
        values('HTTP Status Code') as Statuses,
        values('API Gateway Latency ms') as Latencies,
        values('API Gateway Rate Remaining') as 'Rate Remaining',
        values('API Gateway Threat Signal') as 'Threat Signals',
        values('Trace ID') as Traces
  by 'Attack ID', 'API Gateway Action', 'API Gateway Route Family',
     'Client IP', 'Security Severity'
| sort -'Last Seen'

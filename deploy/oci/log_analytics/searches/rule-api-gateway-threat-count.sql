-- ============================================================================
-- rule-api-gateway-threat-count
-- Deployable Octo rule mirror:
-- oci-log-analytics-detections/apps/apm_octo_rule_api_gateway_threat_count.json
-- ============================================================================
'Attack ID' != null and 'API Gateway Threat Signal' != null
| stats count as ApiGatewayThreatEvents by 'Attack ID', 'Trace ID', 'API Gateway Threat Signal'

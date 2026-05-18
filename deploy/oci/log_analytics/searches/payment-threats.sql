-- ============================================================================
-- payment-threats
-- Octo payment-abuse hunting view aligned with oci-log-analytics-detections
-- apps/apm_octo_payment_threats.json. Keeps four STATS dimensions for OCI LA.
-- ============================================================================
'Attack ID' != null
and ('Payment Interception' != null or 'Payment Redirect' != null or 'Payment Redirect URL' != null)
| stats count as Events,
        distinctcount('Trace ID') as Traces,
        max('Payment Risk Score') as MaxRisk,
        values('Payment Risk Score') as RiskScores,
        values('Payment Card Last4') as CardLast4,
        values('Payment Gateway Request ID') as GatewayRequests,
        values('Transaction ID') as Transactions
  by 'Attack ID', 'Run ID', 'Payment Provider', 'Payment Redirect URL'
| sort -Events

-- ============================================================================
-- rule-payment-interception-count
-- Deployable Octo rule mirror:
-- oci-log-analytics-detections/apps/apm_octo_rule_payment_interception_count.json
-- ============================================================================
'Attack ID' != null and 'Payment Interception' != null
| stats count as PaymentInterceptionEvents by 'Attack ID', 'Trace ID', 'Payment Provider'

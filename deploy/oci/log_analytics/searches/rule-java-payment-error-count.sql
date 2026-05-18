-- ============================================================================
-- rule-java-payment-error-count
-- Deployable Octo rule mirror:
-- oci-log-analytics-detections/apps/apm_octo_rule_java_payment_error_count.json
-- Java sidecar status is also mapped into Response Code for this rule.
-- ============================================================================
'Java APM Error Type' != null
| stats count as JavaPaymentErrorEvents by 'Java APM Error Type', 'Trace ID', 'Response Code'

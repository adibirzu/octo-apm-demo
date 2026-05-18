-- ============================================================================
-- rule-payment-redirect-count
-- Deployable Octo rule mirror:
-- oci-log-analytics-detections/apps/apm_octo_rule_payment_redirect_count.json
-- ============================================================================
'Attack ID' != null and 'Payment Redirect URL' != null
| stats count as PaymentRedirectEvents by 'Attack ID', 'Trace ID', 'Payment Redirect URL'

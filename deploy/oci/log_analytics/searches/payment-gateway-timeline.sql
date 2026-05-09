-- ============================================================================
-- payment-gateway-timeline
-- Real gateway emulator steps from checkout traces and app logs.
-- Parameters: :gateway_request_id optional, :trace_id optional, :order_id optional.
-- ============================================================================
('Payment Gateway Request ID' != null or 'Payment Gateway Step' != null)
| where (:gateway_request_id = null or 'Payment Gateway Request ID' = :gateway_request_id)
| where (:trace_id = null or 'Trace ID' = :trace_id)
| where (:order_id = null or 'Order ID' = :order_id)
| sort Time
| fields Time, Service, 'Trace ID', 'Span ID', 'Order ID',
         'Payment Gateway Request ID', 'Payment Gateway Name',
         'Payment Method', 'Payment Network', 'Payment Card Brand',
         'Payment Wallet Type', 'Payment Gateway Step Index',
         'Payment Gateway Step', 'Payment Gateway Phase',
         'Payment Gateway Step Status', 'Payment Gateway Step Latency ms',
         'Payment Verification Provider', 'Payment Verification Decision',
         'Payment Processor Name', 'Payment Processor Decision',
         'Payment Status', 'Payment Risk Score', 'Original Log Content'

-- ============================================================================
-- payment-risk-decisions
-- Gateway authorization outcomes and antifraud decisions from real checkout logs.
-- ============================================================================
('Payment Gateway Request ID' != null or 'Payment Status' != null)
| where Time > dateRelative(2h)
| stats count as Events,
        values('Payment Gateway Step') as 'Gateway Steps',
        values('Payment Verification Decision') as 'Verification Decisions',
        values('Payment Processor Decision') as 'Processor Decisions',
        max('Payment Risk Score') as 'Max Risk Score',
        values('Trace ID') as Traces,
        values('Order ID') as Orders
  by 'Payment Method', 'Payment Network', 'Payment Card Brand',
     'Payment Wallet Type', 'Payment Status', 'Payment Gateway Request ID'
| sort -'Max Risk Score'

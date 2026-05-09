-- ============================================================================
-- user-order-action-correlation
-- Login, checkout, order, and payment pivots from real app logs.
-- Parameters: :trace_id optional, :auth_user_id optional, :order_id optional.
-- ============================================================================
('Auth User ID' != null or 'Order User ID' != null or 'Order ID' != null)
| where (:trace_id = null or 'Trace ID' = :trace_id)
| where (:auth_user_id = null or 'Auth User ID' = :auth_user_id or 'Order User ID' = :auth_user_id)
| where (:order_id = null or 'Order ID' = :order_id)
| stats count as Events,
        min(Time) as 'First Seen',
        max(Time) as 'Last Seen',
        values('Trace ID') as Traces,
        values('Auth Success') as 'Login Results',
        values('Auth Failure Reason') as 'Login Failure Reasons',
        values('Order ID') as Orders,
        values('Order Customer ID') as Customers,
        values('Payment Gateway Request ID') as 'Gateway Requests',
        values('Payment Status') as 'Payment Statuses',
        values('Security Check') as 'Security Checks'
  by 'Auth User ID', 'Auth Username', 'Auth Role', 'Order User ID'
| sort -'Last Seen'

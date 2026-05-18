-- ============================================================================
-- attack-lab-detections
-- MITRE-tagged attack lab events from Shop, CRM, Java sidecar, and OSQuery logs.
-- ============================================================================
'Attack ID' != null
| where Time > dateRelative(2h)
| stats count as Events,
        min(Time) as 'First Seen',
        max(Time) as 'Last Seen',
        values('Server Address') as Servers,
        values('Host IP Address (Client)') as 'Client IPs',
        values('Destination IP') as 'Destination IPs',
        values('Destination Port') as 'Destination Ports',
        values('MITRE Technique ID') as Techniques,
        values('MITRE Technique') as 'Technique Names',
        values('Instance OCID') as 'Instance OCIDs',
        values('API Gateway Route') as 'API Gateway Routes',
        values('API Gateway Action') as 'API Gateway Actions',
        values('API Gateway Policy Decision') as 'API Gateway Decisions',
        values('API Gateway Threat Signal') as 'API Gateway Threat Signals',
        values('Payment Status') as 'Payment Statuses',
        values('Payment Redirect URL') as 'Payment Redirect URLs',
        values('OSQuery Finding') as Findings
  by 'Attack ID', 'MITRE Tactic', 'Security Severity', 'Compromised VM'
| sort -'Last Seen'

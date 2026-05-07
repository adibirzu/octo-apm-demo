-- ============================================================================
-- osquery-attack-findings
-- OSQuery findings associated with attack-lab runs and Cloud Guard ad-hoc runs.
-- ============================================================================
'OSQuery Query' != null
| where Time > dateRelative(24h)
| stats count as Findings,
        values('OSQuery Finding') as 'Finding Samples',
        values('OSQuery SQL') as 'Query SQL',
        values('MITRE Technique ID') as Techniques,
        values('Attack ID') as 'Attack IDs'
  by 'Host Name', 'Instance OCID', 'OSQuery Query', 'Security Severity'
| sort -Findings

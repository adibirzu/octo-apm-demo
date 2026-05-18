-- ============================================================================
-- rule-compromised-vm-count
-- Deployable Octo rule mirror:
-- oci-log-analytics-detections/apps/apm_octo_rule_compromised_vm_count.json
-- ============================================================================
'Attack ID' != null and 'Compromised VM' != null
| stats count as CompromisedVmEvents by 'Attack ID', 'Compromised VM', 'Host Role'

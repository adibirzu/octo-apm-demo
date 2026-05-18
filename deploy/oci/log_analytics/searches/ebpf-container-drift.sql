-- title: eBPF Container Drift Detection
-- description: Detects unexpected process execution inside application containers using Tetragon eBPF telemetry.
-- schedule: 5
-- severity: HIGH

'Process Name' != null
and ('Pod' like 'shop-%' or 'Pod' like 'crm-%')
and 'Process Name' not in ('/usr/local/bin/python', '/usr/bin/node', '/bin/bash', '/usr/bin/java')
| stats count by 'Pod', 'Process Name', 'Arguments', 'Container ID'
| rename 'Process Name' as 'Unexpected Binary'

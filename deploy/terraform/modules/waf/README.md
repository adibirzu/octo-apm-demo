# WAF module (detection-first)

Additive Terraform module that creates one `oci_waf_web_app_firewall_policy`
per public frontend with:

* OWASP CRS managed protection (log-only by default)
* admin-path CIDR guard (log-only unless `mode = BLOCK`)
* login rate limit (10 / min, action = LOG)
* freeform tags `deployment-profile=portable`, `waf-mode=DETECTION|BLOCK`

## Variables

| name | purpose |
| --- | --- |
| `compartment_id` | compartment OCID |
| `display_name` | policy name |
| `domain` | public hostname (informational, used for tagging + logs) |
| `mode` | `DETECTION` (default) or `BLOCK` |
| `log_group_id` | OCI Logging log group OCID that receives WAF events |
| `admin_allow_cidrs` | CIDRs allowed on `/api/admin/*`; empty = no admin rule emitted |

## Outputs

* `policy_ocid` — attach to your load balancer / WAAS enablement.
* `mode` — normalised to upper case.

## Flipping to BLOCK

1. Observe 7 days of DETECTION logs in Log Analytics (`octo-waf.parser`).
2. Confirm false-positive rate `< 0.1%` on the `waf-top-rules-fired`
   saved search.
3. Update `var.waf_mode = "BLOCK"` and `terraform apply`.
4. The Coordinator `waf-tighten-suggest` playbook posts a proposal
   diff before any apply.

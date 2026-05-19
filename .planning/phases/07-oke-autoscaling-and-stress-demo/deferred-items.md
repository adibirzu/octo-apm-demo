
## 2026-05-18 — Plan 07-10 out-of-scope discoveries

Three pre-existing failures in `tests/test_unified_deploy_surface.py` that
predate Plan 07-10. They assert README.md content (`shop.example.test`,
`crm.example.test`, "public LB/WAF, private Shop and CRM Compute instances,
private ATP", `COMPUTE_RESOURCE_MANAGER_BUTTON_URL`) that has since been
restructured. Not caused by Plan 07-10; deferred for a dedicated docs-drift
fix.

- `test_default_profile_docs_and_examples_target_cyber_sec_ro`
- `test_resource_manager_deploy_button_and_docs_publish_zip_url`
- `test_two_instance_compute_surface_is_offline_validated_and_observable`

Verified pre-existing via `git stash` (failures persist with all Plan 07-10
edits stashed).

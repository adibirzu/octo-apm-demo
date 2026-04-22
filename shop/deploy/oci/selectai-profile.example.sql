-- Starter template for an ATP Select AI profile used by the workflow gateway.
-- Replace the placeholder values, then run as an ATP user with DBMS_CLOUD_AI privileges.
--
-- This template assumes a resource-principal-style credential in OCI-backed environments.
-- If your tenancy uses a different credential model, adjust the credential_name and provider
-- attributes to match your Autonomous Database Select AI setup.

BEGIN
  DBMS_CLOUD_AI.CREATE_PROFILE(
    profile_name => 'OCTO_DRONE_PROFILE',
    attributes   => JSON_OBJECT(
      'provider' VALUE 'oci',
      'credential_name' VALUE 'OCI$RESOURCE_PRINCIPAL',
      'region' VALUE '<oci-region>',
      'oci_compartment_id' VALUE '<compartment-ocid>',
      'model' VALUE '<genai-model-id>',
      'object_list' VALUE JSON_ARRAY(
        'PRODUCTS',
        'CUSTOMERS',
        'ORDERS',
        'ORDER_ITEMS',
        'SHIPMENTS',
        'QUERY_EXECUTIONS',
        'WORKFLOW_RUNS',
        'COMPONENT_SNAPSHOTS'
      ),
      'comments' VALUE 'OCTO workflow gateway Select AI profile',
      'enforce_object_list' VALUE TRUE
    )
  );
END;
/

-- Use this profile name in the application runtime:
--   SELECTAI_PROFILE_NAME=OCTO_DRONE_PROFILE

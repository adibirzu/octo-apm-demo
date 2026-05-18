from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def assert_all_present(text: str, needles: tuple[str, ...], context: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    assert not missing, f"{context} missing: {missing}"


def test_helm_chart_exposes_oke_observability_contract() -> None:
    values = read_text("deploy/helm/octo-apm-demo/values.yaml")
    shop = read_text("deploy/helm/octo-apm-demo/templates/shop-deployment.yaml")
    crm = read_text("deploy/helm/octo-apm-demo/templates/crm-deployment.yaml")

    assert_all_present(
        values,
        (
            "serviceNamespace: octo",
            "stackName: octo-apm-demo",
            "monitoringNamespace: octo_apm_demo",
            "okeClusterName: octo-apm-demo-oke",
            "ociRegion:",
        ),
        "Helm values",
    )

    shared_contract = (
        "SERVICE_NAMESPACE",
        "SERVICE_INSTANCE_ID",
        "DEMO_STACK_NAME",
        "OCI_MONITORING_NAMESPACE",
        "OTEL_RESOURCE_ATTRIBUTES",
        "OTEL_TRACES_SAMPLER",
        "OTEL_PYTHON_LOG_CORRELATION",
        "OTLP_LOG_EXPORT_ENABLED",
        "OCI_AUTH_MODE",
        "OCI_REGION",
        "POD_NAME",
        "POD_NAMESPACE",
        "NODE_NAME",
        "service.namespace={{ .Values.global.serviceNamespace }}",
        "oci.demo.stack={{ .Values.global.stackName }}",
        "k8s.cluster.name={{ .Values.global.okeClusterName }}",
    )
    assert_all_present(shop, shared_contract, "Helm shop deployment")
    assert_all_present(crm, shared_contract, "Helm CRM deployment")

    assert_all_present(
        shop,
        (
            "JAVA_APM_ENABLED",
            "JAVA_APM_SERVICE_URL",
            "JAVA_APM_SERVICE_NAME",
            "PAYMENT_PROVIDER",
            "PAYMENT_GATEWAY_SIMULATION_ENABLED",
            "SELECTAI_PROFILE_NAME",
            "OCI_GENAI_ENDPOINT",
            "OCI_GENAI_MODEL_ID",
            "LANGFUSE_ENABLED",
            "LANGFUSE_HOST",
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
        ),
        "Helm shop payment and GenAI deployment",
    )


def test_helm_chart_deploys_java_payment_gateway_like_raw_oke_manifest() -> None:
    values = read_text("deploy/helm/octo-apm-demo/values.yaml")
    java_template = ROOT / "deploy/helm/octo-apm-demo/templates/java-gateway-deployment.yaml"
    java = java_template.read_text(encoding="utf-8")
    readme = read_text("deploy/helm/octo-apm-demo/README.md")

    assert_all_present(
        values,
        (
            "javaGateway:",
            "repository: octo-apm-java-demo",
            "serviceName: octo-java-app-server-oke",
        ),
        "Helm values Java gateway",
    )
    assert_all_present(
        java,
        (
            "name: octo-apm-java-demo",
            "OCI_APM_SERVICE_NAME",
            "APP_RUNTIME",
            "SERVICE_NAMESPACE",
            "SERVICE_INSTANCE_ID",
            "DEMO_STACK_NAME",
            "OTEL_RESOURCE_ATTRIBUTES",
            "oracle.com/oci_la_log_source_name",
            "SOC Application Logs",
            "kind: Service",
            "kind: PodDisruptionBudget",
        ),
        "Helm Java gateway template",
    )
    assert_all_present(
        readme,
        (
            "octo-apm-java-demo",
            "Java payment gateway",
            "Apple Pay, Google Pay, Visa, and Mastercard",
        ),
        "Helm README Java gateway docs",
    )


def test_vm_and_local_container_deployments_expose_observability_runtime_contract() -> None:
    vm_compose = read_text("deploy/vm/docker-compose-unified.yml")
    vm_env = read_text("deploy/vm/.env.template")
    local_compose = read_text("deploy/local-stack/docker-compose.test.yml")

    shared_vm_contract = (
        "SERVICE_NAMESPACE",
        "SERVICE_INSTANCE_ID",
        "DEMO_STACK_NAME",
        "OCI_REGION",
        "OCI_COMPARTMENT_ID",
        "OCI_MONITORING_NAMESPACE",
        "OTEL_TRACES_SAMPLER",
        "OTEL_PYTHON_LOG_CORRELATION",
        "OTLP_LOG_EXPORT_ENABLED",
        "OCI_LOG_CHAOS_AUDIT_ID",
        "OCI_LOG_SECURITY_ID",
    )
    assert_all_present(vm_compose, shared_vm_contract, "Unified VM compose observability")
    assert_all_present(vm_env, shared_vm_contract, "Unified VM env template observability")

    assert_all_present(
        vm_compose,
        (
            "java-apm:",
            "octo-apm-java-demo",
            "JAVA_APM_ENABLED",
            "JAVA_APM_SERVICE_URL: ${JAVA_APM_SERVICE_URL:-http://java-apm:8080}",
            "PAYMENT_PROVIDER",
            "PAYMENT_GATEWAY_SIMULATION_ENABLED",
            "PAYMENT_SIMULATION_MODE",
            "PAYMENT_SIMULATION_CURRENCY",
            "workflow-gateway:",
            "octo-workflow-gateway",
            "WORKFLOW_API_BASE_URL: ${WORKFLOW_API_BASE_URL:-http://workflow-gateway:8090}",
            "WORKFLOW_PUBLIC_API_BASE_URL: ${WORKFLOW_PUBLIC_API_BASE_URL:-/api/workflow-gateway}",
            "SELECTAI_PROFILE_NAME",
            "OCI_GENAI_ENDPOINT",
            "OCI_GENAI_MODEL_ID",
            "LLMETRY_ENABLED",
            "LANGFUSE_ENABLED",
            "SYNTHETIC_USERS_ENABLED",
        ),
        "Unified VM compose sidecar capabilities",
    )

    assert_all_present(
        local_compose,
        (
            "SERVICE_NAMESPACE: octo",
            "DEMO_STACK_NAME: octo-local-stack",
            "OCI_MONITORING_NAMESPACE: octo_apm_demo",
            "OCI_AUTH_MODE: disabled",
            'OTEL_EXPORTER_OTLP_ENDPOINT: ""',
            "OTLP_LOG_EXPORT_ENABLED: \"false\"",
            "java-apm:",
            "octo-java-app-server-local",
            "PAYMENT_PROVIDER: simulated",
            "PAYMENT_GATEWAY_SIMULATION_ENABLED: \"true\"",
            "LLMETRY_ENABLED: \"true\"",
            "LANGFUSE_ENABLED: \"false\"",
            "SYNTHETIC_USERS_ENABLED: \"true\"",
        ),
        "Local compose safe container capability surface",
    )


def test_oke_raw_manifests_and_helm_chart_share_runtime_capabilities() -> None:
    deploy_script = read_text("deploy/oke/deploy-oke.sh")
    build_script = read_text("deploy/oke/build-push-images.sh")
    raw_shop = read_text("deploy/k8s/oke/shop/deployment.yaml")
    raw_crm = read_text("deploy/k8s/oke/crm/deployment.yaml")
    raw_workflow = read_text("deploy/k8s/oke/workflow-gateway/deployment.yaml")
    workflow_dockerfile = read_text("shop/services/workflow-gateway/Dockerfile")
    helm_values = read_text("deploy/helm/octo-apm-demo/values.yaml")
    helm_shop = read_text("deploy/helm/octo-apm-demo/templates/shop-deployment.yaml")
    helm_crm = read_text("deploy/helm/octo-apm-demo/templates/crm-deployment.yaml")
    helm_workflow = read_text("deploy/helm/octo-apm-demo/templates/workflow-gateway-deployment.yaml")

    assert_all_present(
        deploy_script,
        (
            'apply_manifest "${OKE_DIR}/workflow-gateway/deployment.yaml"',
            "kubectl rollout status deployment/octo-workflow-gateway",
            "kubectl get svc octo-workflow-gateway",
        ),
        "OKE deploy workflow gateway",
    )
    assert_all_present(
        build_script,
        (
            "octo-workflow-gateway",
            "shop/services/workflow-gateway/Dockerfile",
            "verify_runtime_uid octo-workflow-gateway",
        ),
        "OKE image build workflow gateway",
    )

    for content, context in (
        (raw_shop, "raw OKE shop"),
        (raw_crm, "raw OKE CRM"),
        (helm_shop, "Helm shop"),
        (helm_crm, "Helm CRM"),
        (raw_workflow, "raw OKE workflow gateway"),
        (helm_workflow, "Helm workflow gateway"),
    ):
        assert_all_present(
            content,
            (
                "oracle.com/oci_la_log_source_name",
                "SOC Application Logs",
                "oracle.com/oci_la_log_set",
                "octo-apm-demo",
            ),
            context,
        )

    assert 'value: "octo-drone-shop-oke"' in raw_shop
    assert 'value: "enterprise-crm-portal-oke"' in raw_crm
    assert "value: octo-drone-shop-oke" in helm_shop
    assert "value: enterprise-crm-portal-oke" in helm_crm

    assert_all_present(
        raw_shop + helm_shop,
        (
            "WORKFLOW_API_BASE_URL",
            "WORKFLOW_PUBLIC_API_BASE_URL",
            "WORKFLOW_SERVICE_NAME",
            "octo-workflow-gateway",
            "SELECTAI_TIMEOUT_SECONDS",
        ),
        "Shop workflow gateway wiring",
    )
    assert_all_present(
        raw_workflow + helm_workflow + helm_values,
        (
            "WORKFLOW_APP_NAME",
            "WORKFLOW_SERVICE_NAME",
            "octo-workflow-gateway-oke",
            "SERVICE_NAMESPACE",
            "SERVICE_INSTANCE_ID",
            "DEMO_STACK_NAME",
            "OCI_MONITORING_NAMESPACE",
            "OTEL_RESOURCE_ATTRIBUTES",
            "SELECTAI_PROFILE_NAME",
            "workflowGateway:",
            "repository: octo-workflow-gateway",
            "runAsNonRoot: true",
        ),
        "Workflow gateway deployment contract",
    )
    assert_all_present(
        workflow_dockerfile,
        (
            "FROM --platform=$BUILDPLATFORM golang:1.25 AS builder",
            "ARG TARGETOS=linux",
            "ARG TARGETARCH=amd64",
            "GOOS=${TARGETOS} GOARCH=${TARGETARCH}",
        ),
        "Workflow gateway multi-platform build",
    )


def test_release_readiness_documents_offline_and_live_promotion_gates() -> None:
    deploy_readiness = read_text("site/operations/deploy-readiness.md")
    oke_deployment = read_text("site/getting-started/oke-deployment.md")
    combined = deploy_readiness + "\n" + oke_deployment

    assert_all_present(
        combined,
        (
            "bash deploy/verify.sh",
            "bash deploy/compute/validate.sh",
            "APPLY=false",
            "SERVER_DRY_RUN=true",
            "deploy/oke/deploy-oke.sh",
            "deploy/oke/install-oci-kubernetes-monitoring.sh",
            "wire-existing-lb-backends.sh --round-robin-active --apply",
            "--rollback-active-vm",
            "APM Trace Explorer",
            "Log Analytics saved searches",
            "Playwright E2E",
        ),
        "release readiness docs",
    )

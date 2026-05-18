import io
import json
import logging
import os
import requests
import oci
from fdk import response
from opentelemetry import trace

# Configure basic logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
_OTEL_INITIALIZED = False


def _parse_kv(raw):
    values = {}
    for chunk in (raw or "").split(","):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip()
    return values


def _otlp_trace_endpoint(endpoint):
    endpoint = (endpoint or "").rstrip("/")
    if not endpoint:
        return ""
    if endpoint.endswith("/v1/traces") or endpoint.endswith("/private/v1/traces"):
        return endpoint
    if "/20200101" in endpoint:
        return f"{endpoint.split('/20200101', 1)[0]}/20200101/opentelemetry/private/v1/traces"
    return f"{endpoint}/v1/traces"


def _init_otel():
    global _OTEL_INITIALIZED
    if _OTEL_INITIALIZED:
        return trace.get_tracer("octo-auto-remediator")
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:
        return trace.get_tracer("octo-auto-remediator")

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": os.getenv("OTEL_SERVICE_NAME", "octo-auto-remediator"),
                "service.namespace": "octo",
                "deployment.environment": os.getenv("APP_ENV", "production"),
                "cloud.provider": "oci",
                "oci.demo.stack": os.getenv("DEMO_STACK_NAME", "octo-apm-demo"),
            }
        )
    )
    endpoint = _otlp_trace_endpoint(
        os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
        or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        or os.getenv("OCI_APM_ENDPOINT")
        or ""
    )
    headers = _parse_kv(
        os.getenv("OTEL_EXPORTER_OTLP_TRACES_HEADERS")
        or os.getenv("OTEL_EXPORTER_OTLP_HEADERS")
        or ""
    )
    private_key = os.getenv("OCI_APM_PRIVATE_DATAKEY", "")
    if private_key and "Authorization" not in headers:
        headers["Authorization"] = f"dataKey {private_key}"
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, headers=headers)))
    try:
        trace.set_tracer_provider(provider)
    except Exception:
        pass
    RequestsInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)
    _OTEL_INITIALIZED = True
    return trace.get_tracer("octo-auto-remediator")


def handler(ctx, data: io.BytesIO = None):
    tracer = _init_otel()
    try:
        with tracer.start_as_current_span("auto_remediator.handle_alarm") as span:
            # 1. Parse the Alarm Payload
            body = json.loads(data.getvalue())
            logger.info(f"Received Alarm Payload: {json.dumps(body)}")
            span.set_attribute("alarm.type", body.get("type", ""))
            span.set_attribute("alarm.id", body.get("id", ""))
        
            # Only act on FIRING alarms
            alarm_type = body.get("type")
            if alarm_type != "OK_TO_FIRING":
                logger.info(f"Ignoring alarm type: {alarm_type}. Only reacting to OK_TO_FIRING.")
                span.set_attribute("remediation.status", "ignored")
                return response.Response(ctx, response_data=json.dumps({"status": "ignored"}))

            # 2. Extract Configuration from Environment
            compartment_id = os.environ.get("OCI_COMPARTMENT_ID")
            quarantine_nsg_id = os.environ.get("QUARANTINE_NSG_ID")
            genai_endpoint = os.environ.get("OCI_GENAI_ENDPOINT")
            genai_model_id = os.environ.get("OCI_GENAI_MODEL_ID")
            crm_base_url = os.environ.get("CRM_BASE_URL")
        
            if not compartment_id or not quarantine_nsg_id:
                raise ValueError("OCI_COMPARTMENT_ID or QUARANTINE_NSG_ID environment variables are missing.")

            # 3. Authenticate using Resource Principal
            signer = oci.auth.signers.get_resource_principals_signer()
            compute_client = oci.core.ComputeClient(config={}, signer=signer)
            virtual_network_client = oci.core.VirtualNetworkClient(config={}, signer=signer)

            # 4. Find all active Compute Instances in the compartment
            # In a production scenario, we would parse the exact Hostname from the Alarm dimensions.
            # For this demo, we will aggressively quarantine all instances tagged with the 'octo-apm-demo' project.
            logger.info(f"Listing compute instances in compartment: {compartment_id}")
            instances = compute_client.list_instances(compartment_id=compartment_id).data
        
            quarantined_count = 0
            for instance in instances:
                if instance.lifecycle_state != "RUNNING":
                    continue
                
                # Filter to only instances created by our terraform (checking freeform_tags)
                tags = instance.freeform_tags or {}
                if tags.get("project") != "octo-apm-demo":
                    continue

                logger.info(f"Targeting Instance for Quarantine: {instance.display_name} ({instance.id})")
            
                # Find the VNIC attachments for this instance
                vnic_attachments = compute_client.list_vnic_attachments(
                    compartment_id=compartment_id,
                    instance_id=instance.id
                ).data
            
                for attachment in vnic_attachments:
                    vnic_id = attachment.vnic_id
                    # Get current VNIC details
                    vnic = virtual_network_client.get_vnic(vnic_id).data
                    current_nsgs = vnic.nsg_ids or []
                
                    if quarantine_nsg_id not in current_nsgs:
                        # Append the Quarantine NSG to the existing NSGs
                        new_nsgs = current_nsgs + [quarantine_nsg_id]
                        logger.info(f"Applying Quarantine NSG {quarantine_nsg_id} to VNIC {vnic_id}")
                    
                        virtual_network_client.update_vnic(
                            vnic_id,
                            oci.core.models.UpdateVnicDetails(nsg_ids=new_nsgs)
                        )
                        quarantined_count += 1

            logger.info(f"Successfully quarantined {quarantined_count} VNICs.")
            span.set_attribute("remediation.quarantined_vnic_count", quarantined_count)

            # 5. Generative AI Summarization
            summary = "Automated quarantine executed, but AI summarization was not configured."
            if genai_endpoint and genai_model_id:
                try:
                    genai_client = oci.generative_ai_inference.GenerativeAiInferenceClient(
                        config={},
                        signer=signer,
                        service_endpoint=genai_endpoint
                    )
                
                    prompt = (
                        "You are a cybersecurity analyst. Please summarize the following raw eBPF security event payload "
                        "in 3 clear sentences for a non-technical audience. Include the fact that the affected host "
                        f"has been automatically quarantined.\n\nPayload:\n{json.dumps(body)}"
                    )

                    # Cohere command format
                    inference_request = oci.generative_ai_inference.models.CohereLlmInferenceRequest(
                        prompt=prompt,
                        is_stream=False,
                        max_tokens=150,
                        temperature=0.2
                    )
                
                    response_details = oci.generative_ai_inference.models.GenerateTextDetails(
                        compartment_id=compartment_id,
                        serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(
                            model_id=genai_model_id
                        ),
                        inference_request=inference_request
                    )
                
                    ai_response = genai_client.generate_text(response_details)
                    summary = ai_response.data.inference_response.generated_texts[0].text
                    logger.info("AI Summary generated successfully.")
                    span.set_attribute("genai.summary.generated", True)
                except Exception as e:
                    logger.error(f"Failed to generate AI summary: {str(e)}")
                    span.record_exception(e)
                    span.set_attribute("genai.summary.generated", False)
                    summary = f"Automated quarantine executed. Raw payload: {json.dumps(body)}"
        
            # 6. File CRM Ticket
            if crm_base_url:
                try:
                    ticket_payload = {
                        "subject": "[CRITICAL] Automated Security Quarantine Executed",
                        "description": summary,
                        "priority": "critical",
                        "assigned_to": "Security Operations"
                    }
                    # Assume an internal service API or open endpoint for the demo
                    headers = {"Content-Type": "application/json"}
                    res = requests.post(f"{crm_base_url.rstrip('/')}/api/tickets", json=ticket_payload, headers=headers)
                    res.raise_for_status()
                    logger.info(f"Successfully created CRM ticket. Response: {res.json()}")
                    span.set_attribute("crm.ticket.created", True)
                except Exception as e:
                    logger.error(f"Failed to create CRM ticket: {str(e)}")
                    span.record_exception(e)
                    span.set_attribute("crm.ticket.created", False)

            span.set_attribute("remediation.status", "success")
            return response.Response(
                ctx,
                response_data=json.dumps({"status": "success", "quarantined_vnics": quarantined_count}),
                headers={"Content-Type": "application/json"}
            )

    except Exception as e:
        logger.error(f"Error executing auto-remediation: {str(e)}", exc_info=True)
        trace.get_current_span().record_exception(e)
        trace.get_current_span().set_attribute("otel.status_code", "ERROR")
        return response.Response(
            ctx, 
            response_data=json.dumps({"status": "error", "message": str(e)}),
            headers={"Content-Type": "application/json"},
            status_code=500
        )

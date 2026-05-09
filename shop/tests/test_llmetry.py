from __future__ import annotations

from server.observability.llmetry import build_assistant_observation
from server.observability.otel_setup import _langfuse_otlp_traces_endpoint


def test_assistant_llmetry_uses_hashes_not_raw_prompt_content() -> None:
    event, attrs = build_assistant_observation(
        session_id="sess-1",
        message="Can jane@example.test use card 4111 1111 1111 1111 for a Skydio X10?",
        answer="The Skydio X10 supports public safety payloads.",
        provider="oci_genai",
        model_id="cohere.command-r-08-2024",
        usage={"input_tokens": 11, "output_tokens": 7},
        documents_grounded=3,
        guardrail_allowed=True,
        guardrail_reason="catalog_product",
        latency_ms=123.4,
        customer_email="jane@example.test",
    )

    serialized = str({**event, **attrs})
    assert "jane@example.test" not in serialized
    assert "4111 1111 1111 1111" not in serialized
    assert event["prompt_hash"]
    assert event["response_hash"]
    assert attrs["llm.prompt.length"] > 0
    assert attrs["gen_ai.usage.input_tokens"] == 11
    assert attrs["gen_ai.usage.output_tokens"] == 7
    assert attrs["langfuse.observation.type"] == "generation"
    assert attrs["langfuse.project.name"] == attrs["assistant.project.name"]
    assert attrs["langfuse.observation.metadata.project"] == attrs["assistant.project.name"]
    assert attrs["llmetry.project.name"] == attrs["assistant.project.name"]
    assert attrs["langfuse.user.id"] == "domain:example.test"
    assert "project_name" in event["metadata_json"]


def test_langfuse_otlp_endpoint_normalizes_hosts() -> None:
    assert (
        _langfuse_otlp_traces_endpoint("https://langfuse.example.test")
        == "https://langfuse.example.test/api/public/otel/v1/traces"
    )
    assert (
        _langfuse_otlp_traces_endpoint("https://langfuse.example.test/api/public")
        == "https://langfuse.example.test/api/public/otel/v1/traces"
    )
    assert (
        _langfuse_otlp_traces_endpoint("https://langfuse.example.test/api/public/otel/v1/traces")
        == "https://langfuse.example.test/api/public/otel/v1/traces"
    )

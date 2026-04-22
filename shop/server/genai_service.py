"""OCI Generative AI helpers for the drone technical assistant."""

from __future__ import annotations

import asyncio
from typing import Any

import oci

from server.config import cfg


def _build_signer():
    if cfg.oci_auth_mode == "instance_principal":
        return {}, oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    try:
        return {}, oci.auth.signers.get_resource_principals_signer()
    except Exception:
        return oci.config.from_file(), None


def genai_configured() -> bool:
    return bool(cfg.oci_genai_endpoint and cfg.oci_genai_model_id and cfg.oci_compartment_id)


def _chat_sync(message: str, documents: list[dict[str, str]]) -> dict[str, Any]:
    client_config, signer = _build_signer()
    kwargs = {"service_endpoint": cfg.oci_genai_endpoint, "retry_strategy": oci.retry.NoneRetryStrategy()}
    if signer is not None:
        kwargs["signer"] = signer
    client = oci.generative_ai_inference.GenerativeAiInferenceClient(client_config, **kwargs)

    request = oci.generative_ai_inference.models.CohereChatRequest(
        message=message,
        documents=documents,
        preamble_override=(
            "You are OCTO Drone Advisor. Answer only with grounded drone product and operations guidance. "
            "Use ATP catalog facts, be concise, and call out when a detail is not in the catalog."
        ),
        max_tokens=500,
        temperature=0.2,
        prompt_truncation="AUTO_PRESERVE_ORDER",
        citation_quality="FAST",
    )
    details = oci.generative_ai_inference.models.ChatDetails(
        compartment_id=cfg.oci_compartment_id,
        serving_mode=oci.generative_ai_inference.models.OnDemandServingMode(model_id=cfg.oci_genai_model_id),
        chat_request=request,
    )
    response = client.chat(details)
    payload = response.data
    chat_response = payload.chat_response
    usage = getattr(chat_response, "usage", None)
    return {
        "answer": getattr(chat_response, "text", "") or "",
        "provider": "oci_genai",
        "model_id": getattr(payload, "model_id", cfg.oci_genai_model_id),
        "model_version": getattr(payload, "model_version", ""),
        "usage": {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        },
    }


async def chat_with_documents(message: str, documents: list[dict[str, str]]) -> dict[str, Any]:
    return await asyncio.to_thread(_chat_sync, message, documents)

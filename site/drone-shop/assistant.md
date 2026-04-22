# AI Assistant

OCI GenAI-powered drone advisor with ATP conversation history and product grounding.

## How It Works

1. User sends message via `/api/shop/assistant/query`
2. App fetches relevant products from ATP (filtered by `product_focus`)
3. Products converted to grounding documents
4. Message + documents sent to OCI GenAI (or local fallback)
5. Response stored in ATP (`assistant_messages` table)
6. Conversation history maintained per `session_id`

## Configuration

```bash
OCI_GENAI_ENDPOINT="https://inference.generativeai.<region>.oci.oraclecloud.com"
OCI_GENAI_MODEL_ID="cohere.command-r-plus"
OCI_COMPARTMENT_ID="<compartment-ocid>"
```

Falls back to local product-matching logic if GenAI is not configured.

## API

```
POST /api/shop/assistant/query
{
  "message": "Which drone is best for aerial photography?",
  "session_id": "optional-session-id",
  "product_focus": "camera",
  "customer_email": "optional@example.com"
}
```

## Observability

- Span: `shop.assistant.query` + `shop.assistant.genai`
- Attributes: `assistant.provider`, `assistant.model_id`, `assistant.documents_grounded`
- Metric: `shop.business.assistant.queries`

# octo-rollout-validator

Post-deploy gate that confirms every pod reports the expected image
tag at `/api/version` before automation moves to the next step.

KG-040.

## Usage

```bash
python tools/rollout-validator/validate.py \
    --namespace octo-shop-prod \
    --label-selector app=octo-drone-shop \
    --expected-tag 20260423-abc123 \
    --timeout 300
```

Exits `0` when every pod's `/api/version` returns
`image_tag == "20260423-abc123"`. Exits `1` on timeout.

## Wiring into deploy scripts

Add to `deploy/deploy-shop.sh` after `kubectl rollout status`:

```bash
python tools/rollout-validator/validate.py \
    --namespace "$K8S_NAMESPACE" \
    --label-selector "app=$K8S_DEPLOYMENT" \
    --expected-tag "$TAG" || {
        echo "rollout did NOT converge — paging on-call"
        exit 1
    }
```

Catches the situation where `kubectl rollout status` reports success
but a Deployment's `spec.template.spec.containers[].image` wasn't
updated (a common mistake when editing the manifest by hand without
`envsubst`).

## Why not use `kubectl rollout status`?

`rollout status` checks replica readiness, not image version. A pod
that's Ready but running the old image passes `rollout status` but
serves stale code — this validator catches that.

## KG-022 complementary migration

The shop's `Order` table has a `payment_provider_reference` column but
no index on it. Under the payment gateway webhook path that looks up
orders by that reference, a full-table scan is the default plan
without the index. Recommended migration (Alembic, when added):

```python
# alembic/versions/0XXX_order_pp_ref_index.py
def upgrade() -> None:
    op.create_index(
        "ix_orders_payment_provider_reference",
        "orders",
        ["payment_provider_reference"],
        unique=False,
    )

def downgrade() -> None:
    op.drop_index("ix_orders_payment_provider_reference", table_name="orders")
```

When Alembic baseline lands (a future KG), this migration is the
first one stamped `head`.

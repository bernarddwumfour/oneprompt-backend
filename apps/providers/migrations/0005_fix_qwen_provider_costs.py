# Generated manually — corrects a unit error in 0004_backfill_provider_costs.

"""0004 set Qwen provider costs using per-1M-token figures directly in the
per-1K-token fields (e.g. qwen-turbo $0.50/$1.50, roughly 10,000x the real
$0.00005/1K rate researched for plan 0002) — this made the admin margin
dashboard show every Qwen route as wildly, impossibly unprofitable.

Corrected figures (USD per 1K tokens), derived from the same research:
  qwen-turbo: $0.05/1M input confirmed -> $0.00005/1K; output not
    confirmed, estimated at 4x input (consistent with the ~4-5x
    input/output ratio seen across the Qwen family below).
  qwen3-plus: $0.40/1M input confirmed -> $0.0004/1K; output estimated 4x.
  qwen3-max:  $1.20/$6.00 per 1M confirmed (5x ratio) -> $0.0012/$0.006 per 1K.

These remain illustrative pending direct confirmation against DashScope's
live pricing page, per README's "illustrative, must be validated" note —
but are now at least the right order of magnitude.
"""

from decimal import Decimal

from django.db import migrations

CORRECTED = {
    "qwen-turbo": (Decimal("0.00005"), Decimal("0.00020")),
    "qwen-plus": (Decimal("0.00040"), Decimal("0.00160")),
    "qwen-max": (Decimal("0.00120"), Decimal("0.00600")),
}

# The values 0004 wrote, so this migration can be reversed cleanly.
PREVIOUS = {
    "qwen-turbo": (Decimal("0.500"), Decimal("1.500")),
    "qwen-plus": (Decimal("2.000"), Decimal("6.000")),
    "qwen-max": (Decimal("4.000"), Decimal("16.000")),
}


def apply_fix(apps, schema_editor):
    CapabilityRoute = apps.get_model("providers", "CapabilityRoute")
    for slug, (cost_in, cost_out) in CORRECTED.items():
        CapabilityRoute.objects.filter(slug=slug).update(
            provider_cost_input=cost_in,
            provider_cost_output=cost_out,
        )


def revert_fix(apps, schema_editor):
    CapabilityRoute = apps.get_model("providers", "CapabilityRoute")
    for slug, (cost_in, cost_out) in PREVIOUS.items():
        CapabilityRoute.objects.filter(slug=slug).update(
            provider_cost_input=cost_in,
            provider_cost_output=cost_out,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("providers", "0004_backfill_provider_costs"),
    ]

    operations = [
        migrations.RunPython(apply_fix, revert_fix),
    ]

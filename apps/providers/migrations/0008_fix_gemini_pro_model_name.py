# Generated manually — corrects an invalid model name in 0007_seed_providers_0005.

"""0007 seeded gemini-pro with upstream_model="gemini-3.1-pro", researched via
web search at plan-writing time and flagged there as needing reverification
before enabling real traffic. Once a real GEMINI_API_KEY was configured,
live requests failed with:

    404 NOT_FOUND: models/gemini-3.1-pro is not found for API version
    v1beta, or is not supported for generateContent.

Queried the actual /v1beta/openai/models list against the real key — there
is no "gemini-3.1-pro". Using "gemini-pro-latest" instead: Google's own
stable alias for "whatever the current best Pro-tier model is", the same
pattern already used for "gemini-flash-latest" — this avoids the exact
dated-model-name drift that caused this bug in the first place.

gemini-flash's upstream_model ("gemini-3.5-flash") was confirmed present in
the same live models list — no fix needed there.
"""

from django.db import migrations

NEW_MODEL = "gemini-pro-latest"
PREVIOUS_MODEL = "gemini-3.1-pro"  # so this migration can be reversed cleanly


def apply_fix(apps, schema_editor):
    CapabilityRoute = apps.get_model("providers", "CapabilityRoute")
    CapabilityRoute.objects.filter(slug="gemini-pro").update(
        upstream_model=NEW_MODEL
    )


def revert_fix(apps, schema_editor):
    CapabilityRoute = apps.get_model("providers", "CapabilityRoute")
    CapabilityRoute.objects.filter(slug="gemini-pro").update(
        upstream_model=PREVIOUS_MODEL
    )


class Migration(migrations.Migration):

    dependencies = [
        ("providers", "0007_seed_providers_0005"),
    ]

    operations = [
        migrations.RunPython(apply_fix, revert_fix),
    ]

from decimal import Decimal

from django.db import migrations, models


def seed_cloudflare_route(apps, schema_editor):
    CapabilityRoute = apps.get_model("providers", "CapabilityRoute")
    CapabilityRoute.objects.filter(is_default=True).update(is_default=False)
    CapabilityRoute.objects.filter(slug="fast").update(
        is_active=False,
        is_default=False,
    )
    CapabilityRoute.objects.update_or_create(
        slug="oneprompt-free",
        defaults={
            "label": "OnePrompt Free",
            "description": "Free everyday assistance, powered by Llama 3.2.",
            "provider_key": "cloudflare",
            "upstream_model": "@cf/meta/llama-3.2-3b-instruct",
            "credit_rate_input": Decimal("0.0000"),
            "credit_rate_output": Decimal("0.0000"),
            "provider_cost_input": Decimal("0.000051"),
            "provider_cost_output": Decimal("0.000335"),
            "is_active": True,
            "is_default": True,
            "is_free": True,
            "sort_order": 0,
        },
    )


def unseed_cloudflare_route(apps, schema_editor):
    CapabilityRoute = apps.get_model("providers", "CapabilityRoute")
    CapabilityRoute.objects.filter(slug="oneprompt-free").delete()
    CapabilityRoute.objects.filter(slug="fast").update(
        is_active=True,
        is_default=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("providers", "0008_fix_gemini_pro_model_name"),
    ]

    operations = [
        migrations.AddField(
            model_name="capabilityroute",
            name="is_free",
            field=models.BooleanField(
                default=False,
                help_text="If True, users can invoke this route without wallet credits.",
            ),
        ),
        migrations.AlterField(
            model_name="capabilityroute",
            name="provider_key",
            field=models.CharField(
                choices=[
                    ("stub", "Stub (Dev/Testing)"),
                    ("deepseek", "DeepSeek"),
                    ("qwen", "Qwen (Alibaba)"),
                    ("gemini", "Gemini (Google)"),
                    ("claude", "Claude (Anthropic)"),
                    ("chatgpt", "ChatGPT (OpenAI)"),
                    ("cloudflare", "Cloudflare Workers AI"),
                ],
                help_text="Which adapter class to instantiate.",
                max_length=20,
            ),
        ),
        migrations.RunPython(seed_cloudflare_route, unseed_cloudflare_route),
    ]

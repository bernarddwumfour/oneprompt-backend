from django.db import migrations, models
import django.db.models.deletion


def backfill_amount_credits(apps, schema_editor):
    Purchase = apps.get_model("billing", "Purchase")
    for purchase in Purchase.objects.select_related("credit_pack"):
        purchase.amount_credits = purchase.credit_pack.amount_credits
        purchase.save(update_fields=["amount_credits"])


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0003_seed_ghs_credit_packs"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchase",
            name="amount_credits",
            field=models.DecimalField(
                decimal_places=2,
                help_text="Snapshot of wallet credits granted after successful payment.",
                max_digits=12,
                null=True,
            ),
        ),
        migrations.RunPython(backfill_amount_credits, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="purchase",
            name="amount_credits",
            field=models.DecimalField(
                decimal_places=2,
                help_text="Snapshot of wallet credits granted after successful payment.",
                max_digits=12,
            ),
        ),
        migrations.AlterField(
            model_name="purchase",
            name="credit_pack",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="purchases",
                to="billing.creditpack",
            ),
        ),
    ]

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    label = 'accounts'

    def ready(self):
        from django.db.models.signals import post_migrate

        from apps.accounts.signals import ensure_default_admin

        post_migrate.connect(ensure_default_admin, sender=self)

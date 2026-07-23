import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import EmailVerificationToken, User
from apps.accounts.tests.factories import UserFactory
from apps.credits.models import CreditWallet
from common.jwt import encode_access_token


class SignupTests(TestCase):
    def setUp(self):
        cache.clear()

    def _payload(self, **overrides):
        payload = {
            "email": "new@example.com",
            "password": "testpass123",
            "full_name": "New User",
            "country": "GH",
            "age_confirmed": True,
            "terms_accepted": True,
        }
        payload.update(overrides)
        return payload

    def test_signup_creates_user_and_wallet_with_promotional_grant(self):
        response = self.client.post(
            "/api/v1/auth/signup",
            data=json.dumps(self._payload()),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)

        user = User.objects.get(email="new@example.com")
        self.assertFalse(user.is_email_verified)

        wallet = CreditWallet.objects.get(user=user)
        self.assertEqual(wallet.currency, "GHS")
        self.assertGreater(wallet.balance, Decimal("0"))

    def test_signup_rejects_missing_age_confirmation(self):
        response = self.client.post(
            "/api/v1/auth/signup",
            data=json.dumps(self._payload(age_confirmed=False)),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("age_confirmed", response.json()["errors"])

    def test_signup_rejects_missing_terms_acceptance(self):
        response = self.client.post(
            "/api/v1/auth/signup",
            data=json.dumps(self._payload(terms_accepted=False)),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("terms_accepted", response.json()["errors"])

    def test_signup_rejects_duplicate_email(self):
        self.client.post(
            "/api/v1/auth/signup",
            data=json.dumps(self._payload()),
            content_type="application/json",
        )
        response = self.client.post(
            "/api/v1/auth/signup",
            data=json.dumps(self._payload()),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)


class LoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = UserFactory(email="login@example.com")
        CreditWallet.objects.create(user=self.user, currency="GHS")

    def _login(self, password="testpass123"):
        return self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": "login@example.com", "password": password}),
            content_type="application/json",
        )

    def test_login_success_returns_token_pair(self):
        response = self._login()
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertEqual(data["user"]["email"], "login@example.com")

    def test_login_rejects_wrong_password(self):
        response = self._login(password="wrong-password")
        self.assertEqual(response.status_code, 401)

    def test_login_rate_limit_triggers_after_repeated_failures(self):
        for _ in range(10):
            response = self._login(password="wrong-password")
            self.assertEqual(response.status_code, 401)

        limited = self._login(password="wrong-password")
        self.assertEqual(limited.status_code, 429)


class GoogleLoginTests(TestCase):
    def setUp(self):
        cache.clear()

    def _post(self):
        return self.client.post(
            "/api/v1/auth/google",
            data=json.dumps({"code": "google-one-time-code"}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_google_login_requires_configuration(self):
        response = self._post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "Google login is not configured.")

    @override_settings(
        GOOGLE_CLIENT_ID="web-client-id",
        GOOGLE_CLIENT_SECRET="web-client-secret",
        GOOGLE_REDIRECT_URI="http://localhost:3000",
    )
    @patch("apps.accounts.services.auth_service.requests.get")
    @patch("apps.accounts.services.auth_service.requests.post")
    def test_google_login_creates_local_account_wallet_and_tokens(
        self, token_post, profile_get
    ):
        token_post.return_value = Mock(
            json=lambda: {"access_token": "google-access-token"},
            raise_for_status=lambda: None,
        )
        profile_get.return_value = Mock(
            json=lambda: {
                "email": "google@example.com",
                "name": "Google User",
                "verified_email": True,
            },
            raise_for_status=lambda: None,
        )

        response = self._post()

        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        user = User.objects.get(email="google@example.com")
        self.assertTrue(user.is_email_verified)
        self.assertEqual(user.full_name, "Google User")
        self.assertTrue(CreditWallet.objects.filter(user=user).exists())


class RefreshTokenTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = UserFactory(email="refresh@example.com")
        CreditWallet.objects.create(user=self.user, currency="GHS")
        login_response = self.client.post(
            "/api/v1/auth/login",
            data=json.dumps({"email": "refresh@example.com", "password": "testpass123"}),
            content_type="application/json",
        )
        self.tokens = login_response.json()["data"]

    def test_refresh_rotates_token_and_invalidates_the_old_one(self):
        old_refresh = self.tokens["refresh"]

        response = self.client.post(
            "/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": old_refresh}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        new_refresh = response.json()["data"]["refresh"]
        self.assertNotEqual(new_refresh, old_refresh)

        reuse_response = self.client.post(
            "/api/v1/auth/refresh",
            data=json.dumps({"refresh_token": old_refresh}),
            content_type="application/json",
        )
        self.assertEqual(reuse_response.status_code, 401)


class VerifyEmailTests(TestCase):
    def setUp(self):
        self.user = UserFactory(email="verify@example.com")
        CreditWallet.objects.create(user=self.user, currency="GHS")
        self.token = EmailVerificationToken.create_for_user(self.user)

    def _verify(self, token_str):
        return self.client.post(
            "/api/v1/auth/verify-email",
            data=json.dumps({"token": token_str}),
            content_type="application/json",
        )

    def test_verify_email_marks_user_verified(self):
        response = self._verify(self.token.token)
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_email_verified)

    def test_verify_email_rejects_reuse_of_the_same_token(self):
        self._verify(self.token.token)
        response = self._verify(self.token.token)
        self.assertEqual(response.status_code, 400)

    def test_verify_email_rejects_expired_token(self):
        self.token.expires_at = timezone.now() - timedelta(hours=1)
        self.token.save(update_fields=["expires_at"])
        response = self._verify(self.token.token)
        self.assertEqual(response.status_code, 400)


class MeEndpointTests(TestCase):
    def test_me_requires_authentication(self):
        response = self.client.get("/api/v1/me")
        self.assertEqual(response.status_code, 401)

    def test_me_returns_the_authenticated_user(self):
        user = UserFactory(email="me@example.com")
        CreditWallet.objects.create(user=user, currency="GHS")
        token = encode_access_token(user)

        response = self.client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["user"]["email"], "me@example.com")

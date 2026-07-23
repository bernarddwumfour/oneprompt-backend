from django.urls import path

from apps.accounts.views.auth_views import (
    login_view,
    logout_view,
    me_view,
    forgot_password_view,
    google_login_view,
    refresh_view,
    reset_password_view,
    signup_view,
    verify_email_view,
)

urlpatterns = [
    path("signup", signup_view, name="auth-signup"),
    path("login", login_view, name="auth-login"),
    path("google", google_login_view, name="auth-google"),
    path("logout", logout_view, name="auth-logout"),
    path("refresh", refresh_view, name="auth-refresh"),
    path("verify-email", verify_email_view, name="auth-verify-email"),
    path("forgot-password", forgot_password_view, name="auth-forgot-password"),
    path("reset-password", reset_password_view, name="auth-reset-password"),
]

# /me is registered at the config/urls.py level since it's not under /auth

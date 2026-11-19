from django.shortcuts import redirect
from django.urls import resolve, Resolver404
from .models import AccountPolicy


class AccountSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and not request.path.startswith("/static/"):
            from django.conf import settings
            from django.contrib.auth import logout
            from django.utils import timezone
            now = timezone.now()
            opened = request.session.get("rnc_login_started_at")
            if not isinstance(opened, (float, int)) or now.timestamp() - opened >= settings.SESSION_COOKIE_AGE:
                logout(request)
                return redirect("public_site:login")
        try:
            match = resolve(request.path_info)
        except Resolver404:
            return self.get_response(request)
        if (
            request.user.is_authenticated
            and match.url_name
            not in {"password_change", "password_change_done", "logout"}
            and not request.path.startswith("/static/")
        ):
            if AccountPolicy.objects.filter(
                user=request.user, must_change_password=True
            ).exists():
                return redirect("public_site:password_change")
        response = self.get_response(request)
        if not request.path.startswith("/static/"):
            response["Cache-Control"] = "no-store"
            response["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
            )
        return response

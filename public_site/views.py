from django.contrib.auth.views import LoginView
from django.urls import reverse
from .access import can
from .forms import LoginForm


class RoleLoginView(LoginView):
    template_name = "public_site/login.html"
    authentication_form = LoginForm

    def post(self, request, *args, **kwargs):
        from .accounts import limited

        if limited(request, "login", 10):
            form = self.get_form()
            form.add_error(None, "No se pudo iniciar sesión. Espere unos minutos.")
            return self.form_invalid(form)
        return super().post(request, *args, **kwargs)

    def get_default_redirect_url(self):
        return reverse(
            "public_site:intake_prototype"
            if can(self.request.user, "operate_deliveries")
            else "public_site:home"
        )

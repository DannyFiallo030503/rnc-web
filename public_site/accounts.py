import hashlib
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from .access import require
from .forms import (
    AccountForm,
    SearchForm,
    ChangePasswordForm,
    RecoveryForm,
    NewPasswordForm,
)
from .models import AccountPolicy, AccountMail
from .services import audit


def limited(request, namespace, limit=5):
    # Local MVP limiter. Shared cache required before multi-process deployment.
    ip = request.META.get("REMOTE_ADDR", "")
    account = (
        request.POST.get("email", request.POST.get("username", "")).strip().lower()
    )
    blocked = False
    for identity, maximum in [("ip:" + ip, 60), ("account:" + account, limit)]:
        key = namespace + ":" + hashlib.sha256(identity.encode()).hexdigest()
        if cache.add(key, 1, 600):
            continue
        try:
            blocked = cache.incr(key) > maximum or blocked
        except ValueError:
            pass
    return blocked


def deliver_invitation(user):
    from .services import private_root

    if settings.EMAIL_BACKEND == "django.core.mail.backends.filebased.EmailBackend":
        root = private_root() / "mail"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = settings.PUBLIC_ORIGIN.rstrip("/") + reverse(
        "public_site:password_reset_confirm", kwargs={"uidb64": uid, "token": token}
    )
    send_mail(
        "Establecer contraseña · RNC",
        f"Se ha solicitado establecer una contraseña para su cuenta RNC.\n\n{link}\n\nEl enlace vence en una hora y solo puede utilizarse una vez. Si no reconoce esta solicitud, contacte con soporte.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )


def invitation(user):
    # Queue first: SMTP and account existence do not affect public response time.
    if not AccountMail.objects.filter(user=user, status="pending").exists():
        AccountMail.objects.create(user=user)


class ResetRequest(auth_views.PasswordResetView):
    form_class = RecoveryForm
    template_name = "public_site/account_form.html"
    success_url = reverse_lazy("public_site:password_reset_done")
    extra_context = {
        "heading": "Recuperar acceso",
        "intro": "Indique el correo registrado. Si la cuenta está habilitada, recibirá instrucciones.",
        "submit_label": "Solicitar enlace",
    }

    def form_valid(self, form):
        if not limited(self.request, "reset"):
            for user in get_user_model().objects.filter(
                email__iexact=form.cleaned_data["email"], is_active=True
            ):
                try:
                    invitation(user)
                except Exception:
                    # No tokens, recipient addresses, or SMTP credentials in logs.
                    import logging

                    logging.getLogger(__name__).error(
                        "No se pudo procesar una entrega de correo de recuperación."
                    )
        return redirect(self.success_url)


class PasswordChange(auth_views.PasswordChangeView):
    form_class = ChangePasswordForm
    template_name = "public_site/account_form.html"
    success_url = reverse_lazy("public_site:password_change_done")
    extra_context = {
        "heading": "Cambiar contraseña",
        "intro": "Introduzca su contraseña actual y elija una nueva.",
        "submit_label": "Guardar contraseña",
    }

    def form_valid(self, form):
        response = super().form_valid(form)
        AccountPolicy.objects.filter(user=self.request.user).update(
            must_change_password=False
        )
        audit(self.request.user, "Cambio de contraseña", self.request.user.pk)
        return response


class ResetConfirm(auth_views.PasswordResetConfirmView):
    form_class = NewPasswordForm
    template_name = "public_site/account_form.html"
    success_url = reverse_lazy("public_site:password_reset_complete")
    extra_context = {
        "heading": "Establecer contraseña",
        "intro": "Elija su nueva contraseña. No necesita indicar la anterior para recuperar el acceso.",
        "submit_label": "Guardar contraseña",
    }

    def form_valid(self, form):
        if not self.user.is_active:
            return redirect("public_site:login")
        response = super().form_valid(form)
        AccountPolicy.objects.filter(user=self.user).update(must_change_password=False)
        audit(self.user, "Contraseña establecida por enlace", self.user.pk)
        return response


@require("manage_accounts")
def users(request):
    search_form = SearchForm(request.GET)
    q = search_form.cleaned_data["q"] if search_form.is_valid() else ""
    from django.db.models import OuterRef, Subquery

    queryset = (
        get_user_model()
        .objects.order_by("username")
        .prefetch_related("groups")
        .annotate(
            mail_status=Subquery(
                AccountMail.objects.filter(user_id=OuterRef("pk"))
                .order_by("-created_at")
                .values("status")[:1]
            )
        )
    )
    if search_form.errors:
        queryset = queryset.none()
    if q:
        from django.db.models import Q

        queryset = queryset.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
        )
    return render(
        request,
        "public_site/users.html",
        {
            "page": Paginator(queryset, 12).get_page(request.GET.get("page")),
            "q": q,
            "search_form": search_form,
        },
    )


@require("manage_accounts")
def user_edit(request, pk=None):
    User = get_user_model()
    user = get_object_or_404(User, pk=pk) if pk else User()
    roles = [g.name for g in user.groups.all()] if pk else []
    role = (
        "superadmin"
        if user.is_superuser or "superadmin" in roles
        else next((r for r in ["publisher", "operator"] if r in roles), "reader")
    )
    form = AccountForm(
        request.POST if request.method == "POST" else None,
        instance=user,
        initial={"role": role},
    )
    if request.method == "POST" and form.is_valid():
        # Support privileges are delegated only by existing superadmins.
        from .access import has_admin_access

        target_role = form.cleaned_data["role"]
        if not request.user.check_password(form.cleaned_data["confirm_password"]):
            form.add_error(
                "confirm_password",
                "No se pudo confirmar la operación con esa contraseña.",
            )
        elif not has_admin_access(request.user) and (
            role == "superadmin" or target_role == "superadmin"
        ):
            form.add_error("role", "Solo soporte puede modificar cuentas de soporte.")
        elif pk == request.user.pk and (
            not form.cleaned_data["is_active"] or target_role != "superadmin"
        ):
            form.add_error(
                None, "No puede desactivar ni retirar su propio rol de soporte."
            )
        elif (
            pk
            and role == "superadmin"
            and (not form.cleaned_data["is_active"] or target_role != "superadmin")
            and not User.objects.filter(is_active=True)
            .exclude(pk=pk)
            .filter(groups__name="superadmin")
            .exists()
            and not User.objects.filter(is_superuser=True, is_active=True)
            .exclude(pk=pk)
            .exists()
        ):
            form.add_error(
                None, "Debe permanecer al menos una cuenta de soporte activa."
            )
        else:
            password = form.cleaned_data["initial_password"]
            with transaction.atomic():
                user = form.save(commit=False)
                user.is_superuser = False
                user.is_staff = target_role == "superadmin"
                if password:
                    user.set_password(password)
                elif not pk:
                    user.set_unusable_password()
                user.save()
                from django.contrib.auth.models import Group

                user.groups.set(
                    [Group.objects.get_or_create(name=target_role)[0]]
                    if target_role != "reader"
                    else []
                )
                policy, _ = AccountPolicy.objects.get_or_create(user=user)
                if password:
                    policy.must_change_password = True
                policy.save()
                audit(
                    request.user,
                    "Cuenta actualizada" if pk else "Cuenta creada",
                    user.pk,
                )
            messages.success(request, "Cuenta guardada.")
            if (not pk and not password) or request.POST.get("invite"):
                try:
                    invitation(user)
                    messages.success(
                        request,
                        "Invitación en cola de envío. El servicio de correo procesará la solicitud.",
                    )
                except Exception:
                    messages.error(
                        request,
                        "Cuenta guardada; no se pudo encolar el correo. Puede reintentar la invitación.",
                    )
            return redirect("public_site:users")
    return render(
        request,
        "public_site/account_form.html",
        {
            "form": form,
            "heading": "Editar cuenta" if pk else "Crear cuenta",
            "intro": "Asigne el rol y el correo. Sin contraseña temporal, una cuenta nueva recibe una invitación.",
            "submit_label": "Guardar cuenta",
            "editing_account": bool(pk),
        },
    )

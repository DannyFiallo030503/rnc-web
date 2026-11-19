"""Explicit locale for public cached shells and JavaScript catalogs."""
from functools import wraps
from django.conf import settings
from django.utils import translation
from django.views.i18n import JavaScriptCatalog

def localized(view):
    @wraps(view)
    def render(request, *args, **kwargs):
        language = request.GET.get("__rnc_locale")
        if language not in dict(settings.LANGUAGES):
            return view(request, *args, **kwargs)
        request.LANGUAGE_CODE = language
        with translation.override(language):
            response = view(request, *args, **kwargs)
        response["Content-Language"] = language
        return response
    return render

def javascript_catalog(request):
    language = request.GET.get("lang", translation.get_language())
    if language not in dict(settings.LANGUAGES):
        language = settings.LANGUAGE_CODE
    with translation.override(language):
        response = JavaScriptCatalog.as_view(domain="djangojs")(request)
    response["Content-Language"] = language
    return response

def language_return_path(request):
    query = request.GET.copy()
    query.pop("__rnc_locale", None)
    suffix = query.urlencode()
    return request.path + ("?" + suffix if suffix else "")

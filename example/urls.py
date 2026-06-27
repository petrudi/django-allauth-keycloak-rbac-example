from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic.base import TemplateView

from allauth.account.decorators import secure_admin_login


admin.autodiscover()
admin.site.login = secure_admin_login(admin.site.login)

urlpatterns = [
    path("", TemplateView.as_view(template_name="index.html"), name="index"),
    path("accounts/", include("allauth.urls")),
    path("api/", include("example.oidc_provider.urls")),
    path("accounts/profile/", TemplateView.as_view(template_name="profile.html")),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("", include("allauth.idp.urls")),
]

if settings.DEMO_APPS_ENABLED:
    urlpatterns += [
        path("notes/", include("example.demo_notes.urls")),
        path("todos/", include("example.demo_todos.urls")),
    ]

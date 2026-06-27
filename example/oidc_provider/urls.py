from django.urls import path

from .views import OIDCProviderDetailView, OIDCProviderListView

urlpatterns = [
    path("oidc-providers/", OIDCProviderListView.as_view(), name="oidc-provider-list"),
    path("oidc-providers/<name>/", OIDCProviderDetailView.as_view(), name="oidc-provider-detail"),
]

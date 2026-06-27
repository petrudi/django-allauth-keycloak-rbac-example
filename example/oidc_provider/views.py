import json

from django.contrib.auth.mixins import UserPassesTestMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .models import OIDCProvider


def _serialize(provider: OIDCProvider) -> dict:
    return {
        "name": provider.name,
        "client_id": provider.client_id,
        "endpoint_discovery": provider.endpoint_discovery,
        "issuer": provider.issuer,
        "is_active": provider.is_active,
    }


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff


@method_decorator(csrf_exempt, name="dispatch")
class OIDCProviderListView(StaffRequiredMixin, View):
    def get(self, request):
        providers = OIDCProvider.objects.all()
        return JsonResponse({"results": [_serialize(p) for p in providers]})

    def post(self, request):
        data = json.loads(request.body or "{}")
        provider = OIDCProvider.objects.create(
            name=data["name"],
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            endpoint_discovery=data["endpoint_discovery"],
            issuer=data.get("issuer"),
            is_active=data.get("is_active", True),
        )
        return JsonResponse(_serialize(provider), status=201)


@method_decorator(csrf_exempt, name="dispatch")
class OIDCProviderDetailView(StaffRequiredMixin, View):
    def get(self, request, name):
        provider = get_object_or_404(OIDCProvider, name=name)
        return JsonResponse(_serialize(provider))

    def patch(self, request, name):
        provider = get_object_or_404(OIDCProvider, name=name)
        data = json.loads(request.body or "{}")
        for field in ("client_id", "client_secret", "endpoint_discovery", "issuer", "is_active"):
            if field in data:
                setattr(provider, field, data[field])
        provider.save()
        return JsonResponse(_serialize(provider))

    def delete(self, request, name):
        provider = get_object_or_404(OIDCProvider, name=name)
        provider.delete()
        return JsonResponse({}, status=204)

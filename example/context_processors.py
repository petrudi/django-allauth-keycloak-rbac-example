from django.conf import settings


def demo_apps(request):
    """Make DEMO_APPS_ENABLED available in all templates."""
    return {
        "DEMO_APPS_ENABLED": settings.DEMO_APPS_ENABLED,
    }

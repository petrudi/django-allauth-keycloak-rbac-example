from django.db import models

from example.oidc_provider.stubs import OsUserStub


class OIDCProvider(models.Model):
    name = models.CharField(max_length=255, unique=True)
    client_id = models.CharField(max_length=255, unique=True)
    client_secret = models.CharField(max_length=16384)
    endpoint_discovery = models.URLField()
    issuer = models.URLField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        OsUserStub.configure_sssd(self)

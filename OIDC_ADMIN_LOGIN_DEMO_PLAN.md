# OIDC Admin Login — Demo Plan (Keycloak Example Project)

## Goal
Demonstrate the NSG4 OIDC admin login plan in this standalone project. No linux_manager here.

**Demo scope (v1):** OIDC login flow only — no SSH/OS user creation. linux_manager stubs
are kept as no-ops to show where those calls will go in NSG4, but are not exercised.

---

## What this demo proves
| NSG4 concept | Demo equivalent | In scope? |
|---|---|---|
| `user_type = LOCAL` | Django `User` with usable password (existing behavior) | ✅ |
| `user_type = OAUTH` | Django `User` with `is_oidc = True` flag + unusable password | ✅ |
| `token/login` (local) | Django session login (`/accounts/login/`) | ✅ |
| `token/login` blocked for OIDC users | `AccountAdapter.pre_authenticate()` | ✅ |
| OIDC user username collision check | `KeycloakRoleAdapter.pre_social_login()` | ✅ |
| `OIDCProvider` model in nsg_auth | `OIDCProvider` model in this project | ✅ |
| Login UI showing both options | Navbar dropdown + login page hint | ✅ |
| linux_manager OS user creation | — deferred, no stub needed for demo | ❌ v2 |
| SSSD sync on provider save | — deferred, no stub needed for demo | ❌ v2 |
| SSH into device with LDAP creds | — deferred, requires real linux_manager | ❌ v2 |

---

## Files to change / create

### 1. `example/users/models.py` — add `is_oidc` flag
```python
class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    phone = models.CharField(max_length=16, unique=True, blank=True, null=True)
    phone_verified = models.BooleanField(default=False)
    is_oidc = models.BooleanField(default=False)  # True = created via OIDC, no local password
```

### 2. `example/oidc_provider/` — new app (equivalent of nsg_auth OIDCProvider)

**`example/oidc_provider/models.py`**
```python
class OIDCProvider(models.Model):
    name = models.CharField(max_length=255, unique=True)
    client_id = models.CharField(max_length=255, unique=True)
    client_secret = models.CharField(max_length=16384)
    endpoint_discovery = models.URLField()
    issuer = models.URLField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
```

> **v2:** `save()` will call `linux_manager_configure_sssd()` here. Not needed for demo.

**`example/oidc_provider/views.py`** — CRUD for OIDCProvider (admin-only)
```python
# OIDCProviderListView  → GET (list) + POST (create)
# OIDCProviderDetailView → GET + PATCH + DELETE  (lookup: name)
# Both require is_staff=True
```

**`example/oidc_provider/urls.py`**
```python
urlpatterns = [
    path("oidc-providers/",        OIDCProviderListView.as_view(),         name="oidc-provider-list"),
    path("oidc-providers/<name>/", OIDCProviderDetailView.as_view(),       name="oidc-provider-detail"),
]
```

Add to root `example/urls.py`:
```python
path("api/", include("example.oidc_provider.urls")),
```

---

### 3. `example/adapters.py` — extend `KeycloakRoleAdapter`

Add to existing `KeycloakRoleAdapter`:

**`pre_social_login()`** — add collision check before existing role extraction:
```python
def pre_social_login(self, request, sociallogin):
    username = sociallogin.account.extra_data.get("preferred_username")
    if username:
        existing = User.objects.filter(username=username).first()
        if existing and not existing.is_oidc:
            raise ImmediateHttpResponse(
                HttpResponseForbidden("Username exists as a local user.")
            )
    # ... existing role extraction logic unchanged ...
```

**`save_user()`** — override to tag user:
```python
def save_user(self, request, sociallogin, form=None):
    user = super().save_user(request, sociallogin, form)
    user.is_oidc = True
    user.set_unusable_password()
    user.save()
    # v2: OsUserStub.create_locked_user(user.username)
    return user
```

---

### 4. `example/users/allauth.py` — block local login for OIDC users

In existing `AccountAdapter`, override `authentication_failed()` or add to
`login()` to block `is_oidc=True` users from local password login:

```python
def is_open_for_signup(self, request):
    return True  # OIDC users created via save_user, not signup form

def pre_authenticate(self, request, **credentials):
    username = credentials.get("username") or credentials.get("email")
    if username:
        try:
            user = User.objects.get(username=username)
            if user.is_oidc:
                raise ValidationError("This account uses OIDC login. Use 'Sign in with Keycloak'.")
        except User.DoesNotExist:
            pass
```

---

### 5. `example/settings.py` — register new app

```python
INSTALLED_APPS = [
    ...
    "example.oidc_provider",   # new
]
```

---

### 6. Login UI — show both local and OIDC options

The current login page (`/accounts/login/`) already renders the allauth entrance layout which
shows **both** the local username+password form and the "Sign in with Keycloak" provider button
automatically — no template change needed for the main login page as long as both providers
are configured.

**What needs to change:**

#### A. `example/templates/allauth/layouts/base.html` — navbar "Sign In" button
The current navbar has a single "Sign In" link. Update it to show both options as a dropdown:

```html
<!-- replace the single Sign In anchor with a dropdown -->
<li class="nav-item dropdown">
  <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">
    Sign In
  </a>
  <ul class="dropdown-menu dropdown-menu-end">
    <li><a class="dropdown-item" href="{% url 'account_login' %}">Local account</a></li>
    <li><a class="dropdown-item" href="{% url 'keycloak_login' %}">Sign in with Keycloak (OIDC)</a></li>
  </ul>
</li>
```

#### B. Django admin — support OIDC login

Django admin (`/admin/`) uses its own login form, separate from allauth. Two options:

1. **Recommended:** Use allauth's `secure_admin_login` decorator (already applied in `urls.py`)
   which redirects `/admin/login/` through allauth — so the admin login page already shows
   the Keycloak button. No change needed here.

2. **Block OIDC users from admin password prompt:** Since OIDC users have unusable passwords,
   Django admin will reject them automatically if they try the local form. The Keycloak button
   on the admin login page is the correct path for them.

**Verify:** After `secure_admin_login` is active, visiting `/admin/` when logged out redirects
to `/accounts/login/` which shows both local form and Keycloak button. OIDC users click
Keycloak, get redirected back, and land in admin if `is_staff=True`.

#### C. `example/templates/account/login.html` — optional hint for OIDC users
Override allauth's login template to add a helper message below the local form:

```
example/templates/account/login.html
```
```html
{% extends "allauth/account/login.html" %}
{% block content %}
  {{ block.super }}
  <p class="text-center text-muted mt-3">
    If your account was created via Keycloak, use "Sign in with Keycloak" above.
  </p>
{% endblock %}
```

---

## Coexistence guarantee

| Login path | User type | Works? |
|---|---|---|
| `/accounts/login/` (username+password) | `is_oidc=False` (existing) | ✅ unchanged |
| `/accounts/login/` (username+password) | `is_oidc=True` (OIDC user) | ❌ blocked with clear message |
| `/accounts/oidc/keycloak/login/` | `is_oidc=True` | ✅ works |
| `/accounts/oidc/keycloak/login/` username collides with local user | — | ❌ rejected in `pre_social_login` |

---

## Migration
```bash
python manage.py makemigrations users oidc_provider
python manage.py migrate
```

---

## Implementation order
1. `example/users/models.py` — add `is_oidc` field + migration
2. `example/oidc_provider/` — new app: model, views, urls (no stubs for v1)
3. `example/adapters.py` — collision check + `save_user` override
4. `example/users/allauth.py` — block local login for OIDC users
5. `example/settings.py` — add new app
6. `example/templates/allauth/layouts/base.html` — Sign In dropdown (local + Keycloak)
7. `example/templates/account/login.html` — hint for OIDC users

---

## Verification
1. Run `make migrate && make runserver`
2. `POST /api/oidc-providers/` → provider created in DB
3. Navbar shows Sign In dropdown with both options
4. `/accounts/login/` shows local form + Keycloak button + hint message
5. Sign in via Keycloak → user created with `is_oidc=True`, unusable password
6. Try `/accounts/login/` with OIDC username → blocked with clear message
7. Create local user in Django admin, try Keycloak login with same username → rejected
8. `/admin/` when logged out → redirects to allauth login showing both options
9. OIDC user with `is_staff=True` → clicks Keycloak → lands in Django admin
10. Existing local user login → unchanged, still works

## Out of scope (v2)
- linux_manager OS user creation with locked password
- SSSD configuration sync on provider save
- SSH into device with LDAP credentials

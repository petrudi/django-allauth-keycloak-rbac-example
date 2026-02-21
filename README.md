# django-allauth-keycloak-rbac-example

A Django example application demonstrating **role-based access control (RBAC)** using
[django-allauth](https://github.com/pennersr/django-allauth) and
[Keycloak](https://www.keycloak.org/) as an OpenID Connect (OIDC) identity provider.

> **Inspired by** the official django-allauth example:
> [codeberg.org/allauth/django-allauth · examples/regular-django](https://codeberg.org/allauth/django-allauth/src/branch/main/examples/regular-django)
>
> This project extends that base with Keycloak integration, client-level role mapping,
> and fine-grained per-resource authorization enforced in Django views.

---

## What this project demonstrates

- OIDC SSO login via Keycloak using django-allauth's `openid_connect` provider
- Mapping Keycloak **client roles** to Django-side permissions
- Role-based access tiers (`none` / `read` / `read-write`) for demo **Notes** and **Todos** apps
- A custom `SocialAccountAdapter` that extracts roles from the OIDC token
- Docker Compose setup with Keycloak 26, PostgreSQL (for Keycloak), and the Django app

### `ALLAUTH_REGULAR_DEMO_APPS`

This environment variable controls whether the demo **Notes** and **Todos** apps are activated.

When set to `1`, Django includes `example.demo_notes` and `example.demo_todos` in
`INSTALLED_APPS`. These are the apps that demonstrate RBAC — without them the project
runs as a plain django-allauth setup with no role-gated content.

It must be set to `1` whenever you want to explore the Keycloak role-based access features.
It defaults to `0` (off) so the base django-allauth functionality works without Keycloak.

---

## The RBAC problem — and how this project solves it

### The problem

Imagine you have a web application with two sections: **Notes** and **Todos**.
You want different users to have different levels of access:

- One user can read and write Notes, but cannot see Todos at all
- Another user can only read Notes (no creating or deleting), and has full access to Todos
- A third user has no access to either

This is **Role-Based Access Control (RBAC)**: instead of checking "who is this user?",
you check "what roles does this user have?" and decide what they can do based on those roles.

### The traditional problem

In a typical Django app you would hard-code permissions in the database or in code.
That means every time you add a user or change what they can do, a developer has to update the app.
This does not scale, and mixing identity management with your application logic is fragile.

### How this project solves it

This project delegates **identity and role assignment entirely to Keycloak**. The Django app
itself stores no permissions — it only reads what Keycloak says in the login token.

Here is the full flow when `demo_user` logs in:

```
Browser → Keycloak login page
       ← Keycloak issues an ID token containing:
            resource_access.demo_client.roles = ["notes:read-write", "todos:none"]

Django (KeycloakRoleAdapter.pre_social_login)
  → extracts roles from the ID token
  → stores them in request.session["kc_roles"]

Django view (e.g. GET /notes/)
  → reads kc_roles from session
  → finds "notes:read-write" → access granted ✓

Django view (e.g. GET /todos/)
  → reads kc_roles from session
  → finds "todos:none" → access denied ✗
```

### Permission matrix for the demo apps

Each app (`notes`, `todos`) has three role tiers:

| Role | GET (list/read) | POST (create/write) | POST (delete/toggle) |
|---|---|---|---|
| `<app>:read-write` | ✅ allowed | ✅ allowed | ✅ allowed |
| `<app>:read` | ✅ allowed | ❌ 403 | ❌ 403 |
| `<app>:none` | ⚠️ 200 with error message | ❌ 403 | ❌ 403 |
| _(no role)_ | ❌ 403 | ❌ 403 | ❌ 403 |

> The `GET` to the list page returns 200 even with `none` — the view catches the
> `PermissionDenied` and renders a user-friendly "Access Denied" message in the HTML
> instead of a bare error page. All write operations (`POST`) return a hard 403.

**`demo_user` as configured in `kc_config_demo.json`:**

| App | Role | Result |
|---|---|---|
| Notes | `notes:read-write` | can list, create, and delete notes |
| Todos | `todos:none` | sees "Access Denied" on the page; all write endpoints return 403 |

---

## Running with Docker Compose

### 1. Create the environment file

```sh
cat > .env << 'EOF'
ADMIN_PASS="admin_change_me"
ADMIN_REALM="master"
ADMIN_USER="admin"
ALLAUTH_REGULAR_DEMO_APPS=1
DEMO_CLIENT_ID="demo_client"
DEMO_REALM_NAME="demo_realm"
DEMO_USER="demo_user"
DEMO_USER_PASSWORD="demo_change_me"
EXPORT_FILE="./kc_config_demo.json"
IF_RESOURCE_EXISTS="OVERWRITE"
DEMO_CLIENT_SECRET=demo-secret-change-me-1234567890
KEYCLOAK_BASE_URL="http://localhost:8080"
KEYCLOAK_URL="http://localhost:8080"
USERS_DEFAULT_PASSWORD="ChangeMe_12345"
USERS_PASSWORD_TEMPORARY="false"
EOF
```

### 2. Start all services

```sh
docker compose -p regular-django \
  --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.keycloak.yml \
  up --force-recreate
```

This starts:
- **web** — Django app on [http://localhost:8000](http://localhost:8000)
- **keycloak** — Keycloak 26 on [http://localhost:8080](http://localhost:8080)
- **postgres** — PostgreSQL backing Keycloak

### 3. Initialize Keycloak

Once the containers are up, bootstrap the realm, client, roles, and demo user automatically:

```sh
set -a && source .env && set +a
python kc_bootstrap.py
```

Or follow the manual setup guide in [KEYCLOAK.md](KEYCLOAK.md).

---

## Running in development mode

Use this when you want to run Django locally (e.g. with a debugger) while Keycloak
runs in Docker.

### 1. Start only the Keycloak stack

```sh
docker compose -p regular-django \
  --env-file .env \
  -f docker-compose.keycloak.yml \
  up
```

### 2. Set up a Python virtual environment

```sh
git clone <this-repo-url>
cd django-allauth-keycloak-rbac-example
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure local settings

Create `example/local_settings.py` to connect Django with Keycloak:

```python
import os

KEYCLOAK_BASE_URL = os.getenv("KEYCLOAK_BASE_URL", "http://localhost:8080")
CLIENT_SECRET = os.getenv("DEMO_CLIENT_SECRET")
REALM_NAME = os.getenv("DEMO_REALM_NAME", "demo_realm")
CLIENT_ID = os.getenv("DEMO_CLIENT_ID", "demo_client")

SOCIALACCOUNT_PROVIDERS = {
    "openid_connect": {
        "OAUTH_PKCE_ENABLED": True,
        "APPS": [
            {
                "provider_id": "keycloak",
                "name": "Keycloak",
                "client_id": CLIENT_ID,
                "secret": CLIENT_SECRET,
                "settings": {
                    "server_url": f"{KEYCLOAK_BASE_URL}/realms/{REALM_NAME}/.well-known/openid-configuration",
                },
            },
        ],
    }
}

SOCIALACCOUNT_ADAPTER = "example.adapters.KeycloakRoleAdapter"
```

### 4. Load environment variables and run

```sh
set -a && source .env && set +a
export ALLAUTH_REGULAR_DEMO_APPS=1

python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Open [http://localhost:8000](http://localhost:8000) and sign in via Keycloak.

---

## Switching between Docker web and local Django

If you started the full stack with Docker Compose and want to switch to local Django for debugging:

```sh
# Stop only the web container, keep Keycloak running
docker compose -p regular-django stop web

# Then run Django locally as shown in step 4 above
```

---

## Testing RBAC

### In the browser

This is the fastest way to see RBAC in action. The login happens through Keycloak's own
login page — Django never sees your password.

**1. Sign in**

Open [http://localhost:8000](http://localhost:8000) and click **Sign in with Keycloak**.
Enter `demo_user` / `demo_change_me`. Keycloak redirects you back to the app, and the
ID token carrying the user's roles is silently handed to Django in the background.

**2. Click Todos — access denied**

Back on the home page you see two demo apps: **Todos** and **Notes**. Click **Todos**.

Because `demo_user` has the role `todos:none`, the page loads but shows:

```
⚠ Access Denied: No access to todos
```

The page still returns HTTP 200 — the app shows a friendly message rather than a
blank error page — but the todo list is empty and the create form is hidden.

**3. Go back and click Notes — full access**

Click **Back to Home**, then click **Notes**. This time you land on the full Notes page
with a **Create New Note** form visible. Fill in a title and content and click
**Save Note** — the note is saved and appears in the list.

This is RBAC in action: same user, same session, two different resources, two different
outcomes — driven entirely by the roles Keycloak put in the login token.


**Response summary for `demo_user`**

| Endpoint | Method | Role | HTTP | Outcome |
|---|---|---|---|---|
| `/todos/` | GET | `todos:none` | 200 | page with "Access Denied" message |
| `/todos/` | POST | `todos:none` | 403 | Forbidden |
| `/todos/<pk>/toggle/` | POST | `todos:none` | 403 | Forbidden |
| `/todos/<pk>/delete/` | POST | `todos:none` | 403 | Forbidden |
| `/notes/` | GET | `notes:read-write` | 200 | note list |
| `/notes/` | POST | `notes:read-write` | 302 | note created, redirect |
| `/notes/<pk>/delete/` | POST | `notes:read-write` | 302 | note deleted, redirect |

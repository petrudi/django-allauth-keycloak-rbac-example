# Keycloak Setup Guide

This guide covers two paths for configuring Keycloak to work with this project:

- **[Automated](#automated-setup-kc_bootstrappy)** — run `kc_bootstrap.py` to configure everything via the Keycloak Admin REST API
- **[Manual](#manual-setup-admin-console)** — step-by-step walkthrough through the Keycloak Admin Console

---

## Target result

After completing either path you will have:

| Resource | Value |
|---|---|
| Realm | `demo_realm` |
| OIDC Client | `demo_client` (confidential, standard flow) |
| Client roles | `todos:none`, `todos:read`, `todos:read-write`, `notes:none`, `notes:read`, `notes:read-write` |
| Demo user | `demo_user` with roles `todos:none` + `notes:read-write` |
| Protocol mapper | Client roles mapped into the ID token under `resource_access.<client_id>.roles` |

---

## Automated setup (`kc_bootstrap.py`)

The bootstrap script uses `kc_config_demo.json` as a declarative export and applies it via
the Keycloak partial-import API. It then sets user passwords and role mappings.

### Prerequisites

```sh
pip install requests
```

Keycloak must be running and reachable (e.g. via Docker Compose).

### Environment variables

All variables are read from the environment (or your `.env` file).

| Variable | Required | Default | Description |
|---|---|---|---|
| `KEYCLOAK_URL` | yes | — | Base URL of Keycloak, e.g. `http://localhost:8080` |
| `KEYCLOAK_AUTH_PREFIX` | no | `""` | Set to `/auth` for older Keycloak installations behind a reverse proxy |
| `ADMIN_USER` | yes | — | Keycloak admin username |
| `ADMIN_PASS` | yes | — | Keycloak admin password |
| `ADMIN_REALM` | no | `master` | Realm used to authenticate the admin |
| `DEMO_REALM_NAME` | yes | — | Name of the realm to create/update |
| `DEMO_CLIENT_ID` | yes | — | Client ID to inject the secret into |
| `DEMO_CLIENT_SECRET` | yes | — | Client secret injected into the partial import payload |
| `EXPORT_FILE` | yes | — | Path to the export JSON file (e.g. `./kc_config_demo.json`) |
| `IF_RESOURCE_EXISTS` | no | `OVERWRITE` | How to handle conflicts: `OVERWRITE`, `SKIP`, or `FAIL` |
| `DEMO_USER` | no | `demo_user` | Username of the demo user (overrides the value in the export file) |
| `DEMO_USER_PASSWORD` | no | `""` | Password set specifically on `demo_user` after import |
| `USERS_DEFAULT_PASSWORD` | no | `""` | Fallback password for all users listed in `EXPORT_FILE` that have no inline password |
| `USERS_PASSWORD_TEMPORARY` | no | `false` | If `true`, users must change their password on first login |
| `USERS_PASSWORD_FIELD` | no | `""` | Optional field name inside the user object in the export JSON to read the password from |

### Run

```sh
set -a && source .env && set +a
python kc_bootstrap.py
```

On success the script prints `[done]` and echoes the client secret so you can verify it.

### How it works

1. Authenticates against the Keycloak Admin REST API using `ADMIN_USER` / `ADMIN_PASS`
2. Creates `DEMO_REALM_NAME` if it does not exist
3. Runs a partial import from `EXPORT_FILE` — this creates the client, client roles, and protocol mapper
4. Injects `DEMO_CLIENT_SECRET` into the client (replacing the placeholder value in the JSON)
5. Creates each user from the `users` list in `EXPORT_FILE` and assigns their client roles
6. Sets `DEMO_USER_PASSWORD` on `demo_user` (separate step, after the import loop)

### Export file format (`kc_config_demo.json`)

```json
{
  "format": "kc-demo-export-v1",
  "realm": "demo_realm",
  "partial": { ... },   // passed as-is to Keycloak's partialImport endpoint
  "users": [
    {
      "user": { "username": "...", "email": "...", ... },
      "role_mappings": {
        "clients": {
          "demo_client": [
            { "name": "todos:none" },
            { "name": "notes:read-write" }
          ]
        }
      }
    }
  ]
}
```

---

## Manual setup (Admin Console)

Use this if you prefer to configure Keycloak through the browser UI, or if the bootstrap
script is not an option in your environment.

**Prerequisites:**
- Keycloak is running and reachable in your browser (e.g. `http://localhost:8080`)
- You have admin credentials for the `master` realm
- Your Django app is reachable at `http://localhost:8000`

---

### 1. Create the realm

1. Open the Keycloak Admin Console
2. In the top-left realm dropdown, choose **Create realm**
3. Set:
   - **Realm name:** `demo_realm`
   - **Enabled:** ON
4. Click **Create**

---

### 2. Create the client

1. Go to **Clients** → **Create client**
2. Set:
   - **Client type:** OpenID Connect
   - **Client ID:** `demo_client`
3. Click **Next**
4. On the capability config screen, set:
   - **Client authentication:** ON
   - **Standard flow:** ON
   - **Direct access grants:** OFF
   - **Service accounts:** OFF
5. Click **Save**

---

### 3. Configure URLs

Go to **Clients** → `demo_client` → **Settings**.

**Root / Base / Admin URLs:**

| Field | Value |
|---|---|
| Root URL | `http://localhost:8000` |
| Base URL | `http://localhost:8000/` |
| Admin URL | `http://localhost:8000` |

**Valid redirect URIs** — add:
```
http://localhost:8000/accounts/oidc/keycloak/login/callback/
```

**Web origins** — add:
```
http://localhost:8000
```

**Post logout redirect URIs** — add:
```
http://localhost:8000/
```

Also set **Frontchannel logout:** ON.

Click **Save** after each section (or once at the end, depending on your Keycloak version).

---

### 4. Copy the client secret

1. Go to **Clients** → `demo_client` → **Credentials**
2. Copy the **Client secret** value
3. Set it in your `.env` as `DEMO_CLIENT_SECRET=<copied-value>`

---

### 5. Add the client roles protocol mapper

This step is critical — without it, Keycloak will not include client roles in the ID token.

1. Go to **Clients** → `demo_client` → **Client scopes**
2. Click on the dedicated scope (usually `demo_client-dedicated`)
3. Click **Add mapper** → **By configuration** → **User Client Role**
4. Configure:

   | Field | Value |
   |---|---|
   | Name | `client roles` |
   | Client ID | `demo_client` |
   | Token Claim Name | `resource_access.${client_id}.roles` |
   | Add to ID token | ON |
   | Add to access token | ON |
   | Add to userinfo | OFF (optional) |
   | Multivalued | ON |

5. Click **Save**

---

### 6. Create client roles

1. Go to **Clients** → `demo_client` → **Roles**
2. Create each of the following roles (click **Create role**, enter the name exactly including the colon, click **Save**):

   - `notes:none`
   - `notes:read`
   - `notes:read-write`
   - `todos:none`
   - `todos:read`
   - `todos:read-write`

---

### 7. Create the demo user

1. Go to **Users** → **Create new user**
2. Fill in:

   | Field | Value |
   |---|---|
   | Username | `demo_user` |
   | Email | `demo@demo.com` |
   | First name | `demo_name` |
   | Last name | `demo_last_name` |
   | Email verified | ON |
   | Enabled | ON |

3. Click **Create**

---

### 8. Set the user password

1. Go to **Users** → `demo_user` → **Credentials**
2. Click **Set password**
3. Enter a password, set **Temporary:** OFF
4. Click **Save**

---

### 9. Assign client roles to the demo user

1. Go to **Users** → `demo_user` → **Role mapping**
2. Click **Assign role**
3. Switch the filter to **Filter by clients**
4. Select client: `demo_client`
5. Assign:
   - `todos:none`
   - `notes:read-write`
6. Click **Assign**

---

### 10. Verify the setup

| Check | Where |
|---|---|
| All 6 client roles exist | **Clients** → `demo_client` → **Roles** |
| `demo_user` has `todos:none` + `notes:read-write` | **Users** → `demo_user` → **Role mapping** |
| Redirect URI includes the callback URL | **Clients** → `demo_client` → **Settings** |
| Protocol mapper exists on the dedicated scope | **Clients** → `demo_client` → **Client scopes** → `demo_client-dedicated` |

---

## How roles reach Django

After a successful OIDC login, the ID token contains:

```json
{
  "resource_access": {
    "demo_client": {
      "roles": ["todos:none", "notes:read-write"]
    }
  }
}
```

The custom adapter in [example/adapters.py](example/adapters.py) (`KeycloakRoleAdapter`) reads
these roles from the ID token claims during `pre_social_login`, stores them in
`request.session["kc_roles"]`, and persists them in the social account's `extra_data`.
Django views then check these roles to enforce per-resource access tiers.

---

## Security notes

- Never commit the client secret to source control — keep it in `.env` (which is gitignored)
- Prefer **least privilege**: assign only the minimum roles each user needs
- `USERS_PASSWORD_TEMPORARY=false` is fine for local development; set to `true` in any shared or staging environment

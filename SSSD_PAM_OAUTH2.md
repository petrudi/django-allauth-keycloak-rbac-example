# Real OS Login via Keycloak (pam_oauth2_device)

This document is the **real, host-level** counterpart to `OsUserStub` in
`example/oidc_provider/stubs.py`. The Django demo only logs what it *would*
do (`create_locked_user`, `configure_sssd`); this guide wires actual `sudo`
authentication on your Linux machine to Keycloak, without `linux_manager`.

## Why not SSSD itself

SSSD has no native OIDC backend — only `ad`, `ipa`, `ldap`, `krb5`, `proxy`.
There is no `id_provider = oidc` option. Getting SSSD itself talking to
Keycloak would require fronting Keycloak with LDAP/Kerberos federation
(FreeIPA or Keycloak's own LDAP storage provider), which is a much bigger
lift than this demo warrants.

Instead we use **`pam_oauth2_device`** — a PAM module that does the OAuth2
device-code flow at auth time and is independent of SSSD. It authenticates
existing local Linux users; it does not provision them. Provisioning is
`OsUserStub.create_locked_user`, which **does** run real `useradd`/`usermod`
now (see [Provisioning real OS users](#provisioning-real-os-users-create_locked_user)
below) — `pam_oauth2_device` just needs the account to already exist.

## Scope of this setup

Configured for `sudo` only — not login/sshd — so a misconfiguration costs
you `sudo`, never your session. Console/SSH login is untouched.

**Run all of the following yourself, in a real terminal with sudo access.**
These steps need network access and an interactive sudo password prompt,
neither of which the agent's sandboxed shell has.

---

## 1. Install build dependencies

The original/upstream project is
[ICS-MU/pam_oauth2_device](https://github.com/ICS-MU/pam_oauth2_device);
its last commit is several years old. Use the actively maintained fork
[stfc/pam_oauth2_device](https://github.com/stfc/pam_oauth2_device)
(UKRI-STFC, commits as recent as March 2026) instead.

```sh
sudo apt-get update
sudo apt-get install -y build-essential git libpam0g-dev libcurl4-openssl-dev libldap-dev
ls /usr/include/ldap.h   # sanity check: must exist before running make
```

## 2. Build and install pam_oauth2_device

```sh
git clone https://github.com/stfc/pam_oauth2_device.git
cd pam_oauth2_device
make
sudo make install
```

This is a plain Makefile build, no cmake. `make install` places
`pam_oauth2_device.so` under `/lib/x86_64-linux-gnu/security/` on
Debian/Ubuntu. If `make install` doesn't detect your distro layout, copy it
manually:

```sh
sudo cp pam_oauth2_device.so /lib/x86_64-linux-gnu/security/
```

## 3. Register a Keycloak client for device-code flow

Unlike a typical web client, `pam_oauth2_device` expects a **confidential**
client (it sends a `client_secret`, see the config in step 4). Using this
project's existing realm (`demo_realm` from `KEYCLOAK.md`):

```sh
python3 - <<'PY'
import requests, os

KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
ADMIN_USER = os.environ["ADMIN_USER"]
ADMIN_PASS = os.environ["ADMIN_PASS"]
REALM = os.environ.get("DEMO_REALM_NAME", "demo_realm")

token = requests.post(
    f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
    data={
        "client_id": "admin-cli",
        "username": ADMIN_USER,
        "password": ADMIN_PASS,
        "grant_type": "password",
    },
).json()["access_token"]

resp = requests.post(
    f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients",
    headers={"Authorization": f"Bearer {token}"},
    json={
        "clientId": "pam-oauth2-device",
        "publicClient": False,
        "standardFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "attributes": {"oauth2.device.authorization.grant.enabled": "true"},
    },
)
print(resp.status_code, resp.text)
PY
```

Then fetch the generated secret (Keycloak admin console: **Clients →
pam-oauth2-device → Credentials → Client secret**, or via the Admin API's
`/clients/{id}/client-secret` endpoint) — you'll need it for step 4.

Or do it manually in the Keycloak admin console: **Clients → Create client**
→ Client ID `pam-oauth2-device` → Client authentication: **on**
(confidential) → under **Advanced**, enable **OAuth 2.0 Device
Authorization Grant**.

Note the realm's device/token/userinfo endpoints from:
```
{KEYCLOAK_URL}/realms/{REALM}/.well-known/openid-configuration
```

## 4. Configure pam_oauth2_device

The config is **JSON**, not INI, and lives at
`/etc/pam_oauth2_device/config.json`:

```sh
sudo mkdir -p /etc/pam_oauth2_device
sudo tee /etc/pam_oauth2_device/config.json > /dev/null <<'JSON'
{
    "oauth": {
        "client": {
            "id": "pam-oauth2-device",
            "secret": "<client secret from step 3>"
        },
        "scope": "openid profile",
        "device_endpoint": "http://localhost:8080/realms/demo_realm/protocol/openid-connect/auth/device",
        "token_endpoint": "http://localhost:8080/realms/demo_realm/protocol/openid-connect/token",
        "userinfo_endpoint": "http://localhost:8080/realms/demo_realm/protocol/openid-connect/userinfo",
        "username_attribute": "preferred_username"
    },
    "users": {
        "demo_user": ["hesam"]
    }
}
JSON
```

The `users` map controls authorization: keys are the provider's
`username_attribute` value (here, Keycloak's `preferred_username` — use
this project's existing `demo_user` account from `KEYCLOAK.md`/`.env`),
values are the local Linux usernames that identity is allowed to
authenticate as.

**`*bypass*` does NOT mean "allow without OAuth2 login."** Despite the
name, every PAM hook (`pam_sm_authenticate`, `pam_sm_setcred`,
`pam_sm_acct_mgmt`) returns `PAM_IGNORE` for a bypassed user — i.e. "treat
this module as absent from the stack." With only one line in
`/etc/pam.d/pamtester` (or `sudo`), `PAM_IGNORE` from the only module in
the stack means **PAM denies the request** ("Permission denied"), not
grants it. `*bypass*` only makes sense in a stack with another module
underneath it (e.g. `pam_unix.so`) that can still authenticate that user a
different way — it's for exempting accounts like `root` from the OAuth2
requirement, not for skipping the flow during testing. Use a real
`"<keycloak-username>": ["<local-username>"]` mapping to actually test the
device-code flow end-to-end.

Set permissions so the file is readable by whatever process actually
invokes PAM. `pamtester` runs unprivileged as your own user; `sudo`/`sshd`
run as root. `0600` root:root (the tightest option) breaks `pamtester`
testing with "File not found" (the module mis-reports a permission error
as missing-file) — use `0644` for this local test setup, since the file
contains a real client secret but this is not a shared machine:

```sh
sudo chmod 644 /etc/pam_oauth2_device/config.json
```

(If this were a shared machine, the safer alternative is
`sudo chown root:<your-user> ... && sudo chmod 640 ...` to scope
readability to one group instead of world-readable.)

## 5. Test safely with pamtester BEFORE touching sudo

Validate the module actually works using a throwaway PAM service, with zero
risk to `sudo`/login:

```sh
sudo apt-get install -y pamtester
sudo tee /etc/pam.d/pamtester > /dev/null <<'EOF'
auth required pam_oauth2_device.so
EOF
pamtester -v pamtester "$(whoami)" authenticate
```

This should print a device-code URL and code. Open the URL in a browser,
log in to Keycloak as `demo_user` (or whichever account you mapped in step
4's `users` config), and `pamtester` should then exit 0 once the module
polls the token endpoint and confirms `is_authorized`. Only proceed to
editing `/etc/pam.d/sudo` once this works end-to-end with a real login —
not with `*bypass*`, which (per the note in step 4) makes this single-line
stack deny instead of allow.

## 6. Edit /etc/pam.d/sudo — THE RISKY STEP

**Back up first, every time:**

```sh
sudo cp /etc/pam.d/sudo /etc/pam.d/sudo.bak-$(date +%s)
```

**Keep a root shell open in a second terminal before editing**, as a
rollback safety net in case `sudo` itself breaks:

```sh
sudo -i
# leave this terminal open and logged in until you've verified sudo works
```

Add the module as `sufficient` (so existing password-based sudo still works
as a fallback — this is intentionally non-destructive). The module reads
`/etc/pam_oauth2_device/config.json` by default, no path argument needed.

**`/etc/pam.d/sudo` already has its own `@include common-auth` line near
the top — do not add a second one.** Insert only this single new line
directly above that existing line:

```
auth sufficient pam_oauth2_device.so
```

The file should end up with exactly **one** `@include common-auth` line
total (the one already there), with the new `auth sufficient` line
immediately above it — not two `@include common-auth` lines. Check with
`grep -c '@include common-auth' /etc/pam.d/sudo` — it must print `1`, not
`2`, after your edit.

## 7. Test sudo

In a **new** terminal (keep the root shell from step 6 open):

```sh
sudo true
```

You should see a device-code URL and code printed to authenticate via
Keycloak in a browser. On success, `sudo true` exits 0.

If `sudo` breaks entirely, restore from the second terminal's root shell:

```sh
cp /etc/pam.d/sudo.bak-<timestamp> /etc/pam.d/sudo
```

## 8. Rollback (remove entirely)

```sh
sudo cp /etc/pam.d/sudo.bak-<timestamp> /etc/pam.d/sudo
sudo rm -rf /etc/pam_oauth2_device
sudo rm /etc/pam.d/pamtester
```

---

## 9. SSH login via Keycloak (optional)

Higher blast radius than `sudo`: if you misconfigure this **while connected
over SSH with no other access**, you can lock yourself out remotely. Only
do this section if you have local console/physical access as a fallback —
check first:

```sh
systemctl is-active sshd   # if you got here via SSH, stop and reconsider
who am i                   # check if your current session is a pts (remote) or tty (console)
```

If `sshd` is currently inactive and you're on a console (`tty`) session,
not a `pts` (pseudo-terminal/remote) session, you're safe to proceed.

### Enable sshd

```sh
sudo systemctl enable --now ssh
systemctl is-active ssh
```

### Back up configs first

```sh
sudo cp /etc/pam.d/sshd /etc/pam.d/sshd.bak-$(date +%s)
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak-$(date +%s)
```

### Edit /etc/pam.d/sshd

Same pattern as `sudo`: `/etc/pam.d/sshd` already has its own
`@include common-auth` line — **do not add a second one.** Insert only
this single new line directly above the existing `@include common-auth`,
so password/key-based SSH auth still works as a fallback:

```
auth sufficient pam_oauth2_device.so
```

Verify with `grep -c '@include common-auth' /etc/pam.d/sshd` — must print
`1`, not `2`, after your edit.

### Edit /etc/ssh/sshd_config

PAM-based challenge/response auth must be enabled for the module to run
during an SSH session:

```sh
sudo sed -i \
  -e 's/^#\?KbdInteractiveAuthentication.*/KbdInteractiveAuthentication yes/' \
  -e 's/^#\?UsePAM.*/UsePAM yes/' \
  /etc/ssh/sshd_config
grep -E 'KbdInteractiveAuthentication|UsePAM|PasswordAuthentication' /etc/ssh/sshd_config
```

(Older sshd versions use `ChallengeResponseAuthentication` instead of
`KbdInteractiveAuthentication` — check `sshd -T 2>&1 | grep -i auth` if
unsure which your version expects.) Leave `PasswordAuthentication` as-is —
don't disable it, so you keep a fallback login method.

### Apply and test

```sh
sudo sshd -t                  # validate config syntax before restarting
sudo systemctl restart ssh
```

From a **second terminal** (don't close your current console session
until this is verified):

```sh
ssh hesam@localhost
```

You should see the device-code prompt during the SSH handshake. Complete
the Keycloak login in a browser as `demo_user` (per the `users` mapping in
`/etc/pam_oauth2_device/config.json`), and the SSH session should open.

### Rollback

```sh
sudo cp /etc/pam.d/sshd.bak-<timestamp> /etc/pam.d/sshd
sudo cp /etc/ssh/sshd_config.bak-<timestamp> /etc/ssh/sshd_config
sudo sshd -t && sudo systemctl restart ssh
```

If you're already locked out of SSH, use the local console session you
kept open to run the rollback above — that's why this section insists on
verifying console access before starting.

---

## Provisioning real OS users (`create_locked_user`)

`OsUserStub.create_locked_user` (`example/oidc_provider/stubs.py`) now runs
real `useradd --create-home` + `usermod --lock` via `sudo -n` (non-interactive)
whenever the `KeycloakRoleAdapter.save_user` adapter hook fires for a new
OIDC login. This only works if the OS user running the Django process is
granted a **narrow, passwordless** sudoers rule for exactly those two
commands — nothing else.

### One-time setup: grant the narrow sudoers rule

Run this yourself (needs root):

```sh
sudo visudo -f /etc/sudoers.d/django-oidc-demo
```

Paste (replace `hesam` with whichever OS user actually runs `manage.py
runserver`):

```
hesam ALL=(root) NOPASSWD: /usr/sbin/useradd --create-home [a-z_][a-z0-9_-]*, /usr/sbin/usermod --lock [a-z_][a-z0-9_-]*
```

`visudo` validates syntax before saving — if it complains, fix the line
before exiting, don't force-save invalid sudoers.

Note: sudoers wildcards (`*`) match across the whole remaining command
line, not per-argument, so this still permits running `useradd
--create-home` with *some* trailing argument, not exactly one matching
the regex in `stubs.py` — the Python-side validation is the real
enforcement boundary; the sudoers rule is defense-in-depth limiting the
command to `useradd`/`usermod` rather than arbitrary root commands.

Verify:

```sh
sudo -n useradd --create-home -h    # should NOT prompt for a password
```

### What it does and doesn't do

- Validates the username against a strict allow-list regex before touching
  the shell (`^[a-z_][a-z0-9_-]{0,31}$`) — refuses anything else, no shell
  injection surface since `subprocess.run` is passed an argv list, never a
  shell string.
- Skips silently (logs `OS user already exists`) if the user already exists
  — safe to call repeatedly, e.g. on re-login.
- Creates the user **locked** (`usermod --lock`) — no password-based login
  is possible for it, matching `is_oidc=True` users being blocked from local
  password login at the Django layer too.
- Does **not** add the user to any group, does **not** grant sudo, does
  **not** touch SSH keys. It is the bare minimum "this Linux account exists"
  step that `pam_oauth2_device` (above) then authenticates against.
- If the sudoers rule isn't installed, this silently logs an error
  (`Failed to create locked OS user`) and the Django login flow continues
  unaffected — a missing OS account never blocks web login.

### Rollback / cleanup

```sh
sudo userdel -r <username>     # removes the user and home dir
sudo rm /etc/sudoers.d/django-oidc-demo   # revoke the passwordless rule
```

---

## Relationship to the Django demo

| Real step here | Django demo equivalent |
|---|---|
| `pam_oauth2_device` auth at `sudo` time | N/A — Django demo only models web login, not OS login |
| Keycloak client `pam-oauth2-device` | Separate from `demo_client` (the web app's OIDC client) |
| Local Linux user must pre-exist | `OsUserStub.create_locked_user` — now real, see above |
| N/A | `OsUserStub.configure_sssd` stub remains a no-op; no real SSSD config exists for OIDC |

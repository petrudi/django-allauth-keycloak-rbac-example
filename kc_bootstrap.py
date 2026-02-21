#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import requests
import urllib.parse
from typing import Any, Dict, List, Optional


def env(name: str, default: Optional[str] = None, required: bool = False) -> str:
    v = os.getenv(name, default)
    if required and (v is None or v.strip() == ""):
        raise SystemExit(f"Missing required env var: {name}")
    return v or ""


def build_base_url() -> str:
    url = env("KEYCLOAK_URL", required=True).rstrip("/")
    prefix = env("KEYCLOAK_AUTH_PREFIX", "").strip()  # "" or "/auth"
    if prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    return f"{url}{prefix}"


def kc_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_token(base: str) -> str:
    admin_realm = env("ADMIN_REALM", "master")
    client_id = env("ADMIN_CLIENT_ID", "admin-cli")
    username = env("ADMIN_USER", required=True)
    password = env("ADMIN_PASS", required=True)

    token_url = f"{base}/realms/{admin_realm}/protocol/openid-connect/token"
    resp = requests.post(
        token_url,
        data={
            "grant_type": "password",
            "client_id": client_id,
            "username": username,
            "password": password,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _get_json(url: str, token: str, *, timeout: int = 60) -> Any:
    r = requests.get(url, headers=kc_headers(token), timeout=timeout)
    r.raise_for_status()
    return r.json()


def realm_exists(base: str, token: str, realm: str) -> bool:
    url = f"{base}/admin/realms/{realm}"
    r = requests.get(url, headers=kc_headers(token), timeout=30)
    return r.status_code == 200


def create_realm(base: str, token: str, realm: str) -> None:
    if realm_exists(base, token, realm):
        print(f"[realm] exists: {realm}")
        return
    url = f"{base}/admin/realms"
    payload = {"realm": realm, "enabled": True}
    r = requests.post(url, headers=kc_headers(token), json=payload, timeout=30)
    if r.status_code not in (201, 204):
        raise SystemExit(f"[realm] create failed: HTTP {r.status_code} {r.text}")
    print(f"[realm] created: {realm}")


def inject_client_secret_in_partial_payload(
    data: Any, *, target_client_id: str, new_secret: str
) -> bool:
    if not isinstance(data, dict):
        return False
    clients = data.get("clients")
    if not isinstance(clients, list):
        return False
    for c in clients:
        if isinstance(c, dict) and c.get("clientId") == target_client_id:
            c["secret"] = new_secret
            return True
    return False


def partial_import_payload(
    base: str, token: str, realm: str, data: Dict[str, Any]
) -> None:
    if_resource_exists = env("IF_RESOURCE_EXISTS", "OVERWRITE").upper()
    if if_resource_exists not in {"SKIP", "OVERWRITE", "FAIL"}:
        raise SystemExit(
            "[partial-import] IF_RESOURCE_EXISTS must be SKIP|OVERWRITE|FAIL"
        )

    data.setdefault("ifResourceExists", if_resource_exists)

    target_client_id = os.getenv("DEMO_CLIENT_ID")
    secret_value = os.getenv("DEMO_CLIENT_SECRET")
    injected = inject_client_secret_in_partial_payload(
        data, target_client_id=target_client_id, new_secret=secret_value
    )
    if not injected:
        print(
            f"[partial-import] warning: could not find clientId '{target_client_id}' to inject secret"
        )

    url = f"{base}/admin/realms/{realm}/partialImport"
    r = requests.post(url, headers=kc_headers(token), json=data, timeout=60)
    if r.status_code not in (200, 201, 204):
        raise SystemExit(f"[partial-import] failed: HTTP {r.status_code} {r.text}")
    print("[partial-import] done")


def create_user(base: str, token: str, realm: str, u: Dict[str, Any]) -> int:
    payload = {
        "username": u.get("username"),
        "firstName": u.get("firstName"),
        "lastName": u.get("lastName"),
        "email": u.get("email"),
        "enabled": bool(u.get("enabled", True)),
        "emailVerified": bool(u.get("emailVerified", False)),
        "attributes": u.get("attributes") or None,
    }
    payload = {k: v for k, v in payload.items() if v is not None}

    url = f"{base}/admin/realms/{realm}/users"
    r = requests.post(url, headers=kc_headers(token), json=payload, timeout=30)
    return r.status_code


def get_user_id(base: str, token: str, realm: str, username: str) -> str:
    q = urllib.parse.urlencode({"username": username, "exact": "true"})
    url = f"{base}/admin/realms/{realm}/users?{q}"
    arr = _get_json(url, token)
    return arr[0]["id"] if arr else ""


def set_password(
    base: str, token: str, realm: str, user_id: str, password: str
) -> None:
    temporary = env("USERS_PASSWORD_TEMPORARY", "false").lower() == "true"
    payload = {"type": "password", "temporary": temporary, "value": password}
    url = f"{base}/admin/realms/{realm}/users/{user_id}/reset-password"
    r = requests.put(url, headers=kc_headers(token), json=payload, timeout=30)
    if r.status_code != 204:
        raise SystemExit(
            f"[password] failed for {user_id}: HTTP {r.status_code} {r.text}"
        )


def get_clients_map(base: str, token: str, realm: str) -> Dict[str, str]:
    url = f"{base}/admin/realms/{realm}/clients?max=1000"
    clients = _get_json(url, token)
    return {c["clientId"]: c["id"] for c in clients if "clientId" in c and "id" in c}


def get_client_role_by_name(
    base: str, token: str, realm: str, client_uuid: str, role_name: str
) -> Optional[Dict[str, Any]]:
    role_name_enc = urllib.parse.quote(role_name, safe="")
    url = f"{base}/admin/realms/{realm}/clients/{client_uuid}/roles/{role_name_enc}"
    r = requests.get(url, headers=kc_headers(token), timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def create_client_role(
    base: str,
    token: str,
    realm: str,
    client_uuid: str,
    role_name: str,
    description: str = "",
) -> None:
    url = f"{base}/admin/realms/{realm}/clients/{client_uuid}/roles"
    payload = {
        "name": role_name,
        "description": description or "",
        "composite": False,
        "clientRole": True,
    }
    r = requests.post(url, headers=kc_headers(token), json=payload, timeout=60)
    if r.status_code in (201, 204, 409):
        return
    raise SystemExit(
        f"[roles] create client role failed: HTTP {r.status_code} {r.text}"
    )


def ensure_and_resolve_client_roles(
    base: str,
    token: str,
    realm: str,
    client_uuid: str,
    roles_from_export: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    resolved: List[Dict[str, Any]] = []
    for r in roles_from_export:
        name = (r or {}).get("name")
        if not name:
            continue
        desc = (r or {}).get("description") or ""

        role_rep = get_client_role_by_name(base, token, realm, client_uuid, name)
        if role_rep is None:
            create_client_role(base, token, realm, client_uuid, name, description=desc)
            role_rep = get_client_role_by_name(base, token, realm, client_uuid, name)

        if role_rep is None:
            raise SystemExit(f"[roles] could not resolve role after create: {name}")

        resolved.append(role_rep)

    return resolved


def assign_client_roles(
    base: str,
    token: str,
    realm: str,
    user_id: str,
    client_uuid: str,
    role_reps: List[Dict[str, Any]],
) -> None:
    if not role_reps:
        return
    url = f"{base}/admin/realms/{realm}/users/{user_id}/role-mappings/clients/{client_uuid}"
    r = requests.post(url, headers=kc_headers(token), json=role_reps, timeout=60)
    if r.status_code not in (204, 200, 201):
        raise SystemExit(
            f"[roles] client mapping failed for {user_id}: HTTP {r.status_code} {r.text}"
        )


def set_demo_user_password_if_exists(base: str, token: str, realm: str) -> None:
    demo_pw = env("DEMO_USER_PASSWORD", "").strip()
    if not demo_pw:
        return

    demo_username = env("DEMO_USER", "demo_user")
    demo_user_id = get_user_id(base, token, realm, demo_username)
    if not demo_user_id:
        print(f"[demo] {demo_username} not found (skipping DEMO_USER_PASSWORD)")
        return

    set_password(base, token, realm, demo_user_id, demo_pw)
    print(f"[demo] DEMO_USER_PASSWORD applied to {demo_username}")


def replace_demo_user_in_export(data: Any) -> None:
    demo_username = env("DEMO_USER", "demo_user")
    users = data.get("users")
    if not isinstance(users, list):
        return
    for item in users:
        u = (item or {}).get("user") if isinstance(item, dict) else None
        if isinstance(u, dict) and u.get("username") == "demo_user":
            u["username"] = demo_username


def import_from_export_file(base: str, token: str) -> None:
    export_path = env("EXPORT_FILE", required=True)
    if not os.path.isfile(export_path):
        raise SystemExit(f"EXPORT_FILE not found: {export_path}")

    data = json.load(open(export_path, "r", encoding="utf-8"))
    replace_demo_user_in_export(data)
    if not isinstance(data, dict) or data.get("format") != "kc-demo-export-v1":
        raise SystemExit("EXPORT_FILE is not in expected format (kc-demo-export-v1)")

    realm = env("DEMO_REALM_NAME", data.get("realm") or "", required=True)

    create_realm(base, token, realm)

    partial = data.get("partial")
    if not isinstance(partial, dict):
        raise SystemExit("EXPORT_FILE missing 'partial' section")
    partial_import_payload(base, token, realm, partial)

    users = data.get("users", [])
    if not isinstance(users, list):
        raise SystemExit("EXPORT_FILE 'users' must be a list")

    clients_map = get_clients_map(base, token, realm)

    default_pw = env("USERS_DEFAULT_PASSWORD", "")
    pw_field = env("USERS_PASSWORD_FIELD", "")

    for item in users:
        u = (item or {}).get("user") if isinstance(item, dict) else None
        if not isinstance(u, dict):
            raise SystemExit("EXPORT_FILE users items must be objects with 'user' dict")

        username = u.get("username")
        if not username:
            raise SystemExit("User missing username in export")

        code = create_user(base, token, realm, u)
        if code == 201:
            print(f"[users] created: {username}")
        elif code == 409:
            print(f"[users] exists (409): {username}")
        else:
            raise SystemExit(f"[users] create failed for {username}: HTTP {code}")

        user_id = get_user_id(base, token, realm, username)
        if not user_id:
            raise SystemExit(f"[users] could not resolve user_id for {username}")

        pw = ""
        if pw_field and isinstance(u.get(pw_field), str) and u[pw_field].strip():
            pw = u[pw_field].strip()
        elif default_pw:
            pw = default_pw
        if pw:
            set_password(base, token, realm, user_id, pw)
            print(f"[users] password set: {username}")

        rm = item.get("role_mappings") or {}
        client_roles = rm.get("clients") or {}

        if isinstance(client_roles, dict):
            applied_any = False
            for client_id, roles in client_roles.items():
                if not roles:
                    continue
                client_uuid = clients_map.get(client_id)
                if not client_uuid:
                    print(
                        f"[roles] warning: clientId not found in realm: {client_id} (skipping for {username})"
                    )
                    continue
                if not isinstance(roles, list):
                    raise SystemExit(
                        f"[roles] invalid roles list for clientId={client_id}"
                    )

                target_role_reps = ensure_and_resolve_client_roles(
                    base, token, realm, client_uuid, roles
                )
                assign_client_roles(
                    base, token, realm, user_id, client_uuid, target_role_reps
                )
                applied_any = True

            if applied_any:
                print(f"[roles] client roles applied: {username}")


def main() -> None:
    base = build_base_url()
    token = get_token(base)

    import_from_export_file(base, token)

    realm = env("DEMO_REALM_NAME", "", required=True)
    set_demo_user_password_if_exists(base, token, realm)

    print("[done]")
    client_id = os.getenv("DEMO_CLIENT_ID")
    secret_val = os.getenv("DEMO_CLIENT_SECRET")
    print(f"KC CLIENT SECRET (demo) for clientId='{client_id}': {secret_val}")


if __name__ == "__main__":
    try:
        import requests  # noqa: F401
    except Exception:
        raise SystemExit("Missing dependency: pip install requests")
    main()

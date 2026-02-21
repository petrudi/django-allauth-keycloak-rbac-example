#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import requests
from typing import Any, Dict, List, Optional


EXPORT_FILE = "./kc_config_demo.json"


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


def headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def get_json(base: str, token: str, path: str, *, allow_404: bool = False) -> Any:
    url = f"{base}{path}"
    resp = requests.get(url, headers=headers(token), timeout=60)
    if allow_404 and resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def list_all_users(
    base: str, token: str, realm: str, page_size: int = 200
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    first = 0
    while True:
        page = get_json(
            base, token, f"/admin/realms/{realm}/users?first={first}&max={page_size}"
        )
        if not page:
            break
        out.extend(page)
        first += page_size
    return out


def prune_client_for_import(c: Dict[str, Any]) -> Dict[str, Any]:
    drop = {
        "id",
        "secret",
        "registrationAccessToken",
        "notBefore",
        "access",
        "authenticationFlowBindingOverrides",
        "authorizationSettings",
    }
    return {k: v for k, v in c.items() if k not in drop}


def prune_group_for_import(g: Dict[str, Any]) -> Dict[str, Any]:
    drop = {"id", "access"}
    return {k: v for k, v in g.items() if k not in drop}


def prune_role_for_import(r: Dict[str, Any]) -> Dict[str, Any]:
    drop = {"id", "containerId"}
    return {k: v for k, v in r.items() if k not in drop}


def export_partial_like(
    base: str, token: str, realm: str, client_id_to_uuid: Dict[str, str]
) -> Dict[str, Any]:
    clients_raw = get_json(base, token, f"/admin/realms/{realm}/clients?max=1000") or []
    clients = [prune_client_for_import(c) for c in clients_raw if isinstance(c, dict)]

    realm_roles_raw = get_json(base, token, f"/admin/realms/{realm}/roles") or []
    realm_roles = [
        prune_role_for_import(r) for r in realm_roles_raw if isinstance(r, dict)
    ]

    client_roles: Dict[str, List[Dict[str, Any]]] = {}
    for client_id, client_uuid in client_id_to_uuid.items():
        roles_raw = (
            get_json(
                base,
                token,
                f"/admin/realms/{realm}/clients/{client_uuid}/roles",
                allow_404=True,
            )
            or []
        )
        if roles_raw is None:
            roles_raw = []
        roles_list = [
            prune_role_for_import(r) for r in roles_raw if isinstance(r, dict)
        ]
        if roles_list:
            client_roles[client_id] = roles_list

    groups_raw = get_json(base, token, f"/admin/realms/{realm}/groups?max=1000") or []
    groups = [prune_group_for_import(g) for g in groups_raw if isinstance(g, dict)]

    idps = (
        get_json(
            base,
            token,
            f"/admin/realms/{realm}/identity-provider/instances",
            allow_404=True,
        )
        or []
    )
    if idps is None:
        idps = []

    client_scopes = (
        get_json(base, token, f"/admin/realms/{realm}/client-scopes", allow_404=True)
        or []
    )
    if client_scopes is None:
        client_scopes = []

    partial = {
        "ifResourceExists": env("IF_RESOURCE_EXISTS", "OVERWRITE").upper(),
        "clients": clients,
        "roles": {
            "realm": realm_roles,
            "client": client_roles,
        },
        "groups": groups,
        "identityProviders": idps,
        "clientScopes": client_scopes,
    }
    return partial


def main() -> None:
    base = build_base_url()
    realm = env("DEMO_REALM_NAME", required=True)
    out_file = env("EXPORT_FILE", EXPORT_FILE)
    page_size = int(env("PAGE_SIZE", "200"))

    token = get_token(base)

    clients_raw = get_json(base, token, f"/admin/realms/{realm}/clients?max=1000") or []
    client_id_to_uuid = {
        c["clientId"]: c["id"] for c in clients_raw if "clientId" in c and "id" in c
    }

    partial = export_partial_like(base, token, realm, client_id_to_uuid)

    users = list_all_users(base, token, realm, page_size=page_size)

    export_users: List[Dict[str, Any]] = []
    for u in users:
        uid = u["id"]

        realm_roles = (
            get_json(
                base, token, f"/admin/realms/{realm}/users/{uid}/role-mappings/realm"
            )
            or []
        )

        client_role_mappings: Dict[str, Any] = {}
        for client_id, client_uuid in client_id_to_uuid.items():
            roles = (
                get_json(
                    base,
                    token,
                    f"/admin/realms/{realm}/users/{uid}/role-mappings/clients/{client_uuid}",
                )
                or []
            )
            if roles:
                client_role_mappings[client_id] = roles

        export_users.append(
            {
                "user": u,
                "role_mappings": {
                    "realm": realm_roles,
                    "clients": client_role_mappings,
                },
            }
        )

    payload = {
        "format": "kc-demo-export-v1",
        "realm": realm,
        "partial": partial,
        "users": export_users,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"[export] wrote: {out_file}")
    print(f"[export] users: {len(export_users)}")
    print(f"[export] clients: {len(client_id_to_uuid)}")
    print(f"[export] realm roles: {len(partial.get('roles', {}).get('realm', []))}")
    print(
        f"[export] client roles (clients with roles): {len(partial.get('roles', {}).get('client', {}))}"
    )
    print("[export] done")


if __name__ == "__main__":
    try:
        import requests  # noqa
    except Exception:
        raise SystemExit("Missing dependency: pip install requests")
    main()

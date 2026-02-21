import os


KEYCLOAK_BASE_URL = os.getenv("KEYCLOAK_BASE_URL")
CLIENT_SECRET = os.getenv("DEMO_CLIENT_SECRET")
REALM_NAME = os.getenv("DEMO_REALM_NAME")
CLIENT_ID = os.getenv("DEMO_CLIENT_ID")

SOCIALACCOUNT_PROVIDERS = {
    "openid_connect": {
        "OAUTH_PKCE_ENABLED": True,
        "APPS": [
            {
                "provider_id": "keycloak",
                "name": "Keycloak",
                "client_id": f"{CLIENT_ID}",
                "secret": f"{CLIENT_SECRET}",
                "settings": {
                    "server_url": f"{KEYCLOAK_BASE_URL}/realms/{REALM_NAME}/.well-known/openid-configuration",
                },
            },
             {
                "provider_id": "other-server",
                "name": "Salam",
                "client_id": "320c9efb-d0e5-423a-bf01-88f74c37f0b4",
                "secret": "YojtD9CeKdtsfdWCij6QHOc8SFSUqU2gQX36511GbYVOZneN2grviQorpC512u1C",
                "settings": {
                    # "server_url": "https://salam-sivan.phoenix.mahsan.net/iam2/.well-known/oauth-authorization-server",
                    "server_url": "https://salam-sivan.phoenix.mahsan.net/iam2/.well-known/openid-configuration",
                    # Scopes from Postman
                    "scope": ["profile", "openid"],
                    # "userinfo_endpoint":"https://actual-userinfo-url.example.com/path",

                    # # Authorization request parameters from Postman: authRequestParams
                    # # "AUTH_PARAMS": {
                    # #     "audience": "http://nsg4/acess"
                    # # },

                    # # Token request parameters from Postman: tokenRequestParams
                    # "TOKEN_PARAMS": {
                    #     "audience": "http://nsg4/acess"
                    # },

                    # # Refresh token request parameters from Postman: refreshRequestParams
                    # "REFRESH_TOKEN_PARAMS": {
                    #     "audience": "http://nsg4/acess"
                    # },

                    # # Client authentication method from Postman: client_authentication: "body"
                    # "TOKEN_AUTH_METHOD": "client_secret_post"
                },
            },
        ],
    },
    
}

# Disable email verification completely
# ACCOUNT_EMAIL_VERIFICATION = "optional"

SOCIALACCOUNT_ADAPTER = "example.adapters.KeycloakRoleAdapter"

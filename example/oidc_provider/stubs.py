import logging
import re
import subprocess

logger = logging.getLogger(__name__)

# Linux usernames: letters/digits/_/- , must not start with a digit or hyphen.
_VALID_USERNAME = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


class OsUserStub:
    @staticmethod
    def create_locked_user(username: str) -> None:
        # In NSG4: AdminUserClient.linux_manager_create_admin_user({"username": username, "locked": True})
        if not _VALID_USERNAME.match(username):
            logger.warning("[OS] Refusing to create OS user with invalid username: %r", username)
            return

        check = subprocess.run(["id", username], capture_output=True)
        if check.returncode == 0:
            logger.info("[OS] OS user already exists, skipping: %s", username)
            return

        try:
            subprocess.run(
                ["sudo", "-n", "useradd", "--create-home", username],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["sudo", "-n", "usermod", "--lock", username],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("[OS] Created locked OS user: %s", username)
        except subprocess.CalledProcessError as e:
            logger.error("[OS] Failed to create locked OS user %s: %s", username, e.stderr)

    @staticmethod
    def configure_sssd(provider: "OIDCProvider") -> None:
        # In NSG4: AdminUserClient.linux_manager_configure_sssd({...})
        logger.info("[STUB] Would configure SSSD for provider: %s", provider.name)

"""Install Kompressor's native Hermes plugin."""

from kompressor.hermes_install.installer import (
    HermesInstallStatus,
    get_hermes_install_status,
    install_hermes_integration,
    prove_hermes_integration,
    uninstall_hermes_integration,
)

__all__ = [
    "HermesInstallStatus",
    "get_hermes_install_status",
    "install_hermes_integration",
    "prove_hermes_integration",
    "uninstall_hermes_integration",
]

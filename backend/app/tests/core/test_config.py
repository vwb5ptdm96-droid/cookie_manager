from app.core.config import Settings


def test_settings_can_boot_with_local_defaults():
    settings = Settings()

    assert settings.app_name == "session-maintenance-system"
    assert settings.runtime_root.name == "runtime"
    assert settings.deploy_root.name == "session-maintenance-system"

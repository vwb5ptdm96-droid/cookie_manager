from app.core.config import Settings


def test_settings_can_boot_with_local_defaults(monkeypatch):
    # 隔离本机 .env 可能配置的真实 key，断言本地默认关闭鉴权
    monkeypatch.setenv("COOKIE_SYNC_API_KEY", "")
    settings = Settings()

    assert settings.app_name == "session-maintenance-system"
    assert settings.runtime_root.name == "runtime"
    assert settings.deploy_root.name == "session-maintenance-system"
    assert settings.cookie_sync_api_key == ""  # 默认关闭鉴权，生产在 .env 配置

from app.core.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES, resolve_locale, t


def test_t_default_locale_zh():
    assert t("bridges.not_found") == "桥梁不存在"


def test_t_with_en_locale():
    assert t("bridges.not_found", locale="en-US") == "Bridge not found"


def test_t_with_params():
    assert t("bridges.exists", name="赵州桥") == "桥梁「赵州桥」已存在"
    assert (
        t("bridges.exists", locale="en-US", name="Zhaozhou Bridge")
        == 'Bridge "Zhaozhou Bridge" already exists'
    )


def test_t_unknown_key_returns_key_itself():
    assert t("nonexistent.key") == "nonexistent.key"
    assert t("nonexistent.key", locale="en-US") == "nonexistent.key"


def test_resolve_locale_whitelists():
    assert resolve_locale("zh-CN") == "zh-CN"
    assert resolve_locale("en-US") == "en-US"
    assert resolve_locale("fr-FR") == DEFAULT_LOCALE
    assert resolve_locale(None) == DEFAULT_LOCALE
    assert resolve_locale("") == DEFAULT_LOCALE


def test_unsupported_locale_uses_default():
    assert t("bridges.not_found", locale="ja-JP") == "桥梁不存在"


def test_zh_en_dicts_key_parity():
    from app.locales import en_us, zh_cn

    zh_keys = set(zh_cn.MESSAGES.keys())
    en_keys = set(en_us.MESSAGES.keys())
    missing_in_en = zh_keys - en_keys
    missing_in_zh = en_keys - zh_keys
    assert not missing_in_en, f"en-US missing keys: {missing_in_en}"
    assert not missing_in_zh, f"zh-CN missing keys: {missing_in_zh}"


def test_supported_locales_constant():
    assert set(SUPPORTED_LOCALES) == {"zh-CN", "en-US"}
    assert DEFAULT_LOCALE == "zh-CN"

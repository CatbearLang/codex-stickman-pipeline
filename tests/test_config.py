"""F1 RED: config segura stickman.toml (plan §4.2) + rechazo de secretos."""
import pytest

from stickman import config


def test_load_config_valida_valores_known(tmp_path):
    p = tmp_path / "stickman.toml"
    p.write_text('[voice]\nprovider = "edge"\n', encoding="utf-8")
    cfg = config.load_config(tmp_path)
    assert cfg["voice"]["provider"] == "edge"


def test_load_config_rechaza_voice_desconocido(tmp_path):
    p = tmp_path / "stickman.toml"
    p.write_text('[voice]\nprovider = "SUBASTA"\n', encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load_config(tmp_path)


def test_script_provider_vacio_permitido_en_memoria(tmp_path):
    cfg = config.default_config()
    cfg["script"]["provider"] = ""
    # validar en memoria no debe fallar por provider vacio (init lo exige)
    assert config.validate_config(cfg) is True


def test_config_set_rechaza_secreto(tmp_path):
    msg = config.config_set(tmp_path, "XAI_API_KEY", "x")
    assert msg.startswith("use environment variable")


def test_config_set_rechaza_api_key_minuscula(tmp_path):
    msg = config.config_set(tmp_path, "voice.api_key", "sk-falso")
    assert msg.startswith("use environment variable")


def test_config_set_roundtrip(tmp_path):
    msg = config.config_set(tmp_path, "voice.provider", "edge")
    assert "ok" in msg.lower() or "guardad" in msg.lower()
    cfg = config.load_config(tmp_path)
    assert cfg["voice"]["provider"] == "edge"


def test_default_target_minutes_es_5_5():
    cfg = config.default_config()
    assert cfg["project"]["target_minutes"] == 5.5
    assert config.validate_config(cfg) is True

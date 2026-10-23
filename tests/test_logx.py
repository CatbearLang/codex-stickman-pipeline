"""F1 RED: logx redacta valores live, conserva identificadores inocuos."""
from stickman import logx

_DUMMY_SK = "sk-" + "abcdef1234567890"


def test_redact_sk():
    s = logx.redact(f"fallo con clave {_DUMMY_SK} en el log")
    assert _DUMMY_SK not in s
    assert "redacted" in s.lower()


def test_redact_xai_y_bearer():
    s = logx.redact("xai-aaaaabbbbbccccc y Bearer zyxW9876543210QQ")
    assert "xai-aaaaabbbbbccccc" not in s
    assert "zyxW9876543210QQ" not in s


def test_redact_no_toca_identificadores():
    s = logx.redact("total_tokens=5 uso de token conteo auth ok")
    assert "total_tokens=5" in s


def test_logger_emite_redactado(tmp_path, capsys):
    logger = logx.get_logger("test-fase1")
    logger.info(f"llamada con {_DUMMY_SK} adentro")
    out = capsys.readouterr().out + capsys.readouterr().err
    assert _DUMMY_SK not in out

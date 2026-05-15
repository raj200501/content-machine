from pathlib import Path

from app.env_sync import append_missing_env_values


def test_append_missing_env_values_preserves_existing_values(tmp_path: Path) -> None:
    example = tmp_path / ".env.example"
    env = tmp_path / ".env"
    example.write_text("A=one\nB=\nC=true\n", encoding="utf-8")
    env.write_text("B=secret\n", encoding="utf-8")

    added = append_missing_env_values(env, example)

    assert added == ("A", "C")
    content = env.read_text(encoding="utf-8")
    assert "B=secret" in content
    assert "A=one" in content
    assert "C=true" in content


def test_append_missing_env_values_is_idempotent(tmp_path: Path) -> None:
    example = tmp_path / ".env.example"
    env = tmp_path / ".env"
    example.write_text("A=one\n", encoding="utf-8")

    assert append_missing_env_values(env, example) == ("A",)
    assert append_missing_env_values(env, example) == ()

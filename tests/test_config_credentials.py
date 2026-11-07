from app.config import Settings


def test_access_token_whitespace_is_removed() -> None:
    settings = Settings(instagram_access_token="  EAAB12\nCD34 \r\n EF56\t", instagram_ig_user_id=" 178 ")
    assert settings.instagram_access_token == "EAAB12CD34EF56"
    assert settings.instagram_ig_user_id == "178"

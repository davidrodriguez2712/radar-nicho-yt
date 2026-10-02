from nicheradar.config import Settings
from nicheradar.domain.profile import CreatorProfile


def test_new_budget_fields_have_conservative_defaults() -> None:
    settings = Settings()
    assert settings.youtube_search_quota_per_run == 100
    assert settings.youtube_search_quota_per_week == 100
    assert settings.youtube_search_quota_per_month == 300
    assert settings.youtube_detail_quota_per_run == 100
    assert settings.youtube_detail_quota_per_week == 500
    assert settings.youtube_detail_quota_per_month == 2000
    profile = CreatorProfile()
    assert profile.channel_analysis_credits_per_run == 50

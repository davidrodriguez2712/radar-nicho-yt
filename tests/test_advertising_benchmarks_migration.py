import sqlalchemy as sa
from sqlalchemy import Connection


def test_advertising_benchmarks_seeded(db: Connection) -> None:
    total = db.execute(sa.text("SELECT count(*) FROM advertising_benchmarks")).scalar_one()
    assert total == 218
    row = (
        db.execute(
            sa.text(
                "SELECT rate_low, rate_high FROM advertising_benchmarks "
                "WHERE niche_label = 'true_crime_stories'"
            )
        )
        .mappings()
        .one()
    )
    assert row["rate_low"] <= row["rate_high"]

from pathlib import Path

import pytest

from boq.rate_catalog import RateCatalog, RateCatalogEntry
from utils.exceptions import BoqValidationError


def test_default_catalog_is_clearly_example_only() -> None:
    catalog = RateCatalog.default()
    entries = catalog.entries()

    assert entries
    assert all(entry.currency == "INR" for entry in entries)
    assert all(entry.source == "example" for entry in entries)
    assert all(entry.rate == 0 for entry in entries)


def test_upsert_remove_and_duplicate_operations() -> None:
    catalog = RateCatalog()
    catalog.add(RateCatalogEntry("wall", "Wall", "m", 100))
    catalog.upsert(RateCatalogEntry("wall", "Wall revised", "m", 125))

    assert catalog.get("wall").name == "Wall revised"
    assert catalog.get("wall").source == "user-entered"

    catalog.remove("wall")
    assert catalog.get("wall") is None

    catalog.add(RateCatalogEntry("wall", "Wall", "m", 100))
    with pytest.raises(BoqValidationError, match="Duplicate"):
        catalog.add(RateCatalogEntry("wall", "Wall duplicate", "m", 200))


def test_csv_round_trip(tmp_path: Path) -> None:
    catalog = RateCatalog(
        (
            RateCatalogEntry("wall", "Wall", "m", 125, currency="INR"),
            RateCatalogEntry("fixture", "Fixture", "nos", 75, currency="INR"),
        )
    )
    csv_text = catalog.to_csv()
    imported = RateCatalog.from_csv_text(csv_text)

    assert imported.get("wall").rate == 125
    assert imported.get("fixture").source == "user-entered"

    path = tmp_path / "rates.csv"
    catalog.export_csv(path)
    reimported = RateCatalog.import_csv(path)
    assert reimported.get("fixture").unit == "nos"


def test_invalid_csv_and_invalid_entry_are_rejected() -> None:
    with pytest.raises(BoqValidationError, match="CSV"):
        RateCatalog.from_csv_text("item_id,name\nwall,Wall")
    with pytest.raises(BoqValidationError, match="non-negative"):
        RateCatalogEntry("wall", "Wall", "m", -10)

"""Editable construction rate catalog with CSV import/export."""

import csv
from io import StringIO
from pathlib import Path

from utils.exceptions import BoqValidationError


class RateCatalogEntry:
    def __init__(
        self,
        item_id: str,
        name: str,
        unit: str,
        rate: float,
        currency: str = "INR",
        source: str = "user-entered",
    ) -> None:
        if not item_id.strip() or not name.strip():
            raise BoqValidationError("Rate catalog item ID and name are required.")
        if not unit.strip():
            raise BoqValidationError("Rate catalog unit is required.")
        if not isinstance(rate, (int, float)) or isinstance(rate, bool):
            raise BoqValidationError("Rate must be numeric.")
        if rate < 0:
            raise BoqValidationError("Rate must be non-negative.")
        if source not in {"example", "user-entered"}:
            raise BoqValidationError("Rate source must be example or user-entered.")

        self.item_id = item_id.strip()
        self.name = name.strip()
        self.unit = unit.strip()
        self.rate = float(rate)
        self.currency = currency.strip().upper()
        if not self.currency:
            raise BoqValidationError("Currency is required.")
        self.source = source

    def to_row(self) -> dict[str, str | float]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "unit": self.unit,
            "rate": self.rate,
            "currency": self.currency,
            "source": self.source,
        }


class RateCatalog:
    """In-memory rate catalog with CSV serialization."""

    def __init__(self, entries: tuple[RateCatalogEntry, ...] = ()) -> None:
        self._entries: dict[str, RateCatalogEntry] = {}
        for entry in entries:
            self.add(entry)

    @classmethod
    def default(cls) -> "RateCatalog":
        """Create clearly labeled zero-rate placeholders, not market prices."""
        placeholders = (
            RateCatalogEntry("wall", "Wall", "m", 0, source="example"),
            RateCatalogEntry("floor", "Floor area", "m2", 0, source="example"),
            RateCatalogEntry("door", "Door", "nos", 0, source="example"),
            RateCatalogEntry("window", "Window", "nos", 0, source="example"),
            RateCatalogEntry("fixture", "Fixture", "nos", 0, source="example"),
        )
        return cls(placeholders)

    def add(self, entry: RateCatalogEntry) -> None:
        if entry.item_id in self._entries:
            raise BoqValidationError(
                f"Duplicate rate catalog item ID: {entry.item_id}"
            )
        self._entries[entry.item_id] = entry

    def upsert(self, entry: RateCatalogEntry) -> None:
        self._entries[entry.item_id] = entry

    def remove(self, item_id: str) -> None:
        if item_id not in self._entries:
            raise BoqValidationError(f"Unknown rate catalog item ID: {item_id}")
        del self._entries[item_id]

    def get(self, item_id: str) -> RateCatalogEntry | None:
        return self._entries.get(item_id)

    def entries(self) -> tuple[RateCatalogEntry, ...]:
        return tuple(self._entries.values())

    def to_csv(self) -> str:
        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=("item_id", "name", "unit", "rate", "currency", "source"),
        )
        writer.writeheader()
        for entry in self.entries():
            writer.writerow(entry.to_row())
        return output.getvalue()

    def export_csv(self, path: str | Path) -> None:
        Path(path).write_text(self.to_csv(), encoding="utf-8")

    @classmethod
    def from_csv_text(cls, text: str) -> "RateCatalog":
        reader = csv.DictReader(StringIO(text))
        required = {"item_id", "name", "unit", "rate", "currency", "source"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise BoqValidationError(
                "CSV must contain item_id, name, unit, rate, currency, and source."
            )
        catalog = cls()
        for row in reader:
            try:
                source = row["source"].strip().lower()
                rate = float(row["rate"])
                catalog.add(
                    RateCatalogEntry(
                        item_id=row["item_id"],
                        name=row["name"],
                        unit=row["unit"],
                        rate=rate,
                        currency=row["currency"],
                        source=source,
                    )
                )
            except (AttributeError, KeyError, TypeError, ValueError) as exc:
                raise BoqValidationError("CSV contains invalid or missing rate data.") from exc
        return catalog

    @classmethod
    def import_csv(cls, path: str | Path) -> "RateCatalog":
        return cls.from_csv_text(Path(path).read_text(encoding="utf-8"))

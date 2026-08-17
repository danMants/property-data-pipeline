from __future__ import annotations

import json
import re
from pathlib import Path

from .models import SourceConfig


_SOURCE_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load_sources(path: str | Path) -> list[SourceConfig]:
    config_path = Path(path)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read source config {config_path}: {exc}") from exc

    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("Source config must contain a non-empty 'sources' list")

    sources: list[SourceConfig] = []
    seen_names: set[str] = set()
    for index, item in enumerate(raw_sources, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Source #{index} must be an object")

        name = item.get("name")
        investment = item.get("investment")
        dataset_id = item.get("dataset_id")
        if not isinstance(name, str) or not _SOURCE_NAME.fullmatch(name):
            raise ValueError(f"Source #{index} has an invalid slug-style name")
        if name in seen_names:
            raise ValueError(f"Duplicate source name: {name}")
        if not isinstance(dataset_id, int) or dataset_id <= 0:
            raise ValueError(f"Source {name} has an invalid dataset_id")
        if not isinstance(investment, str) or not investment.strip():
            raise ValueError(f"Source {name} must define investment")

        column_map = item.get("column_map", {})
        if not isinstance(column_map, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in column_map.items()
        ):
            raise ValueError(f"Source {name} has an invalid column_map")

        sources.append(
            SourceConfig(
                name=name,
                dataset_id=dataset_id,
                investment=investment.strip(),
                district=_optional_text(item.get("district")),
                developer=_optional_text(item.get("developer")),
                column_map=column_map,
            )
        )
        seen_names.add(name)
    return sources


def select_sources(
    sources: list[SourceConfig], requested_names: list[str] | None
) -> list[SourceConfig]:
    if not requested_names:
        return sources
    by_name = {source.name: source for source in sources}
    missing = sorted(set(requested_names) - by_name.keys())
    if missing:
        raise ValueError(f"Unknown source(s): {', '.join(missing)}")
    return [by_name[name] for name in requested_names]


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Optional text fields must be strings")
    stripped = value.strip()
    return stripped or None


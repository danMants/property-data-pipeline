from __future__ import annotations

import csv
import io
import json
from datetime import date
from typing import Any
from urllib.request import Request, urlopen

from .models import ResourceSnapshot, SourceConfig


class DaneGovClient:
    """Small client for the public, read-only dane.gov.pl API."""

    api_base = "https://api.dane.gov.pl/1.4"

    def __init__(self, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = timeout_seconds

    def latest_csv(self, source: SourceConfig) -> tuple[ResourceSnapshot, bytes]:
        endpoint = (
            f"{self.api_base}/datasets/{source.dataset_id}/resources"
            "?sort=-data_date&page=1"
        )
        payload = self._get_json(endpoint)
        candidates: list[ResourceSnapshot] = []
        for item in payload.get("data", []):
            attributes = item.get("attributes", {})
            if str(attributes.get("format", "")).lower() != "csv":
                continue
            observed_on = _parse_api_date(attributes.get("data_date"))
            download_url = _download_url(attributes)
            if observed_on is None or download_url is None:
                continue
            candidates.append(
                ResourceSnapshot(
                    resource_id=str(item["id"]),
                    title=str(attributes.get("title", source.name)),
                    observed_on=observed_on,
                    download_url=download_url,
                )
            )

        if not candidates:
            raise RuntimeError(
                f"Dataset {source.dataset_id} has no downloadable CSV resource"
            )
        latest = max(candidates, key=lambda resource: resource.observed_on)
        return latest, self._get_bytes(latest.download_url)

    def _get_json(self, url: str) -> dict[str, Any]:
        try:
            return json.loads(self._get_bytes(url).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Invalid JSON response from {url}") from exc

    def _get_bytes(self, url: str) -> bytes:
        request = Request(
            url,
            headers={
                "Accept": "application/json,text/csv;q=0.9,*/*;q=0.8",
                "User-Agent": "warsaw-property-data-pipeline/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                content = response.read()
        except OSError as exc:
            raise RuntimeError(f"Failed to download {url}: {exc}") from exc
        if not content:
            raise RuntimeError(f"Empty response from {url}")
        return content


def read_csv_rows(content: bytes) -> list[dict[str, str]]:
    text = _decode_csv(content)
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    return [
        {str(key).strip(): (value or "").strip() for key, value in row.items() if key}
        for row in reader
        if any((value or "").strip() for value in row.values())
    ]


def _decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1250"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV is not valid UTF-8 or Windows-1250 text")


def _parse_api_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _download_url(attributes: dict[str, Any]) -> str | None:
    direct = attributes.get("download_url") or attributes.get("file_url")
    if isinstance(direct, str) and direct.startswith("https://"):
        return direct
    for file_info in attributes.get("files", []):
        candidate = file_info.get("download_url")
        if isinstance(candidate, str) and candidate.startswith("https://"):
            return candidate
    return None


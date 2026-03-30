"""Amap batch geocoding service for bridge coordinates."""

import asyncio
import csv
import io
import logging
from dataclasses import dataclass
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Bridge

logger = logging.getLogger(__name__)


@dataclass
class GeocodeResult:
    bridge_id: UUID
    bridge_name: str
    success: bool
    latitude: float | None = None
    longitude: float | None = None
    raw_address: str = ""
    error: str | None = None


class GeocodeService:
    def __init__(self):
        self.api_key = settings.amap_api_key

    async def _amap_geocode(self, address: str) -> tuple[float, float] | None:
        """Call Amap geocode API. Returns (lat, lng) or None."""
        if not self.api_key:
            raise ValueError("AMAP_API_KEY is not configured")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://restapi.amap.com/v3/geocode/geo",
                params={"key": self.api_key, "address": address, "output": "json"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "1":
                logger.warning(
                    "Amap geocode error for %r: info=%s, infocode=%s",
                    address, data.get("info"), data.get("infocode"),
                )
                return None
            if data.get("geocodes"):
                location = data["geocodes"][0]["location"]  # "lng,lat"
                lng, lat = location.split(",")
                return float(lat), float(lng)
        return None

    async def batch_geocode(
        self, db: Session, bridge_ids: list[UUID] | None = None
    ) -> dict:
        """Geocode bridges using Amap API.

        - bridge_ids=None: geocode bridges with NULL latitude only
        - bridge_ids=[]: geocode ALL bridges (re-geocode)
        - bridge_ids=[id1, id2]: geocode specific bridges

        Returns: {"total": N, "success": N, "failed": N, "results": [...]}
        """
        query = db.query(Bridge)
        if bridge_ids is not None and len(bridge_ids) > 0:
            query = query.filter(Bridge.id.in_(bridge_ids))
        elif bridge_ids is None:
            query = query.filter(Bridge.latitude.is_(None))
        # else: empty list = all bridges, no filter

        bridges = query.all()
        results = []

        for bridge in bridges:
            address = f"{bridge.name} {bridge.region or ''}".strip()
            try:
                coords = await self._amap_geocode(address)
                if coords:
                    lat, lng = coords
                    bridge.latitude = lat
                    bridge.longitude = lng
                    bridge.geocode_source = "amap"
                    results.append(
                        GeocodeResult(
                            bridge_id=bridge.id,
                            bridge_name=bridge.name,
                            success=True,
                            latitude=lat,
                            longitude=lng,
                            raw_address=address,
                        )
                    )
                else:
                    results.append(
                        GeocodeResult(
                            bridge_id=bridge.id,
                            bridge_name=bridge.name,
                            success=False,
                            raw_address=address,
                            error="No geocode result",
                        )
                    )
            except Exception as e:
                logger.error("Geocode failed for %s: %s", bridge.name, e)
                results.append(
                    GeocodeResult(
                        bridge_id=bridge.id,
                        bridge_name=bridge.name,
                        success=False,
                        raw_address=address,
                        error=str(e),
                    )
                )

            await asyncio.sleep(0.2)  # Rate limit: ~5 req/s

        db.flush()
        return {
            "total": len(results),
            "success": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "results": results,
        }

    def import_from_csv(self, db: Session, csv_content: str) -> dict:
        """Import coordinates from CSV. Format: name,latitude,longitude

        Match by exact name. Returns {matched, unmatched}.
        """
        reader = csv.DictReader(io.StringIO(csv_content))
        matched = 0
        unmatched = []

        for row in reader:
            name = row.get("name", "").strip()
            lat = row.get("latitude", "").strip()
            lng = row.get("longitude", "").strip()
            if not name or not lat or not lng:
                continue

            bridge = db.query(Bridge).filter(Bridge.name == name).first()
            if not bridge:
                unmatched.append(name)
                continue

            try:
                bridge.latitude = float(lat)
                bridge.longitude = float(lng)
            except ValueError:
                unmatched.append(f"{name} (invalid coordinates: {lat}, {lng})")
                continue

            bridge.geocode_source = "csv"
            matched += 1

        db.flush()
        return {"matched": matched, "unmatched": unmatched}

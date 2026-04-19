"""Geolocation helpers.

Minimal built-in gazetteer for country → lat/lon. Downstream callers can swap
in a full GeoNames gazetteer when available. GDELT/ACLED articles carry their
own lat/lon; this module is only used when the source does not.
"""
from __future__ import annotations


# (country_code, lat, lon) — approximate centroid for country-level geocoding.
COUNTRY_CENTROIDS: dict[str, tuple[float, float]] = {
    "US": (39.8, -98.6), "RU": (61.5, 105.3), "CN": (35.9, 104.2),
    "UA": (48.4, 31.2), "IL": (31.0, 34.8), "IR": (32.4, 53.7),
    "KP": (40.3, 127.5), "KR": (35.9, 127.8), "JP": (36.2, 138.3),
    "DE": (51.2, 10.4), "FR": (46.6, 2.2), "GB": (55.4, -3.4),
    "IN": (20.6, 78.9), "PK": (30.4, 69.3), "TR": (38.9, 35.2),
    "SY": (34.8, 38.9), "YE": (15.6, 48.5), "LB": (33.9, 35.9),
    "PS": (31.9, 35.2), "SA": (23.9, 45.1), "IQ": (33.2, 43.7),
    "AF": (33.9, 67.7), "TW": (23.7, 120.9), "VE": (6.4, -66.6),
    "CU": (21.5, -77.8), "BY": (53.7, 27.9), "SD": (12.9, 30.2),
    "LY": (26.3, 17.2), "ET": (9.1, 40.5), "SO": (5.2, 46.2),
    "NG": (9.1, 8.7), "MM": (21.9, 95.9),
}


def centroid_for_country(country_code: str | None) -> tuple[float, float] | None:
    if not country_code:
        return None
    return COUNTRY_CENTROIDS.get(country_code.upper())


def build_geojson_point(lat: float | None, lon: float | None) -> dict | None:
    if lat is None or lon is None:
        return None
    return {"type": "Point", "coordinates": [float(lon), float(lat)]}

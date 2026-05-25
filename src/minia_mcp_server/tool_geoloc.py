import datetime
import json
import logging
import urllib.request
from typing import Any

from .mcp_instance import mcp, ToolError

logger = logging.getLogger(__name__)

GEOIP_URL = (
    "http://ip-api.com/json/?fields=status,city,regionName,country,lat,lon,timezone"
)
GEOIP_TIMEOUT = 3  # seconds


@mcp.tool()
def get_current_location() -> dict[str, Any]:
    """Get current geographic location via IP geolocation.

    Returns a dict with location data including city, region, country,
    coordinates, and timezone information.
    """
    try:
        req = urllib.request.Request(
            GEOIP_URL, headers={"User-Agent": "MCP-GeoLocationAgent"}
        )
        with urllib.request.urlopen(req, timeout=GEOIP_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        logger.debug("IP geolocation unavailable: %s", e)
        raise ToolError(str(e))

    if data.get("status") != "success":
        raise ToolError("IP geolocation service returned unsuccessful status")

    return {
        "city": data.get("city", ""),
        "region": data.get("regionName", ""),
        "country": data.get("country", ""),
        "lat": data.get("lat", 0.0),
        "lon": data.get("lon", 0.0),
        "timezone": data.get("timezone", ""),
        "status": "success",
    }


@mcp.tool()
def get_current_time() -> dict[str, Any]:
    """Get current date and timezone information.

    Returns a dict with date, timezone name, and UTC offset.
    """
    now = datetime.datetime.now()
    tz = datetime.datetime.now(datetime.UTC).astimezone().tzinfo

    return {
        "date": now.isoformat(),
        "timezone_name": str(tz),
        "utc_offset": _format_utc_offset(now),
    }


@mcp.tool()
def get_full_context() -> dict[str, Any]:
    """Get complete environmental context including date/time and location.

    Combines time information and geolocation data into a single context dict.
    """
    # Get time context
    time_ctx = get_current_time()

    # Get location context
    location_ctx = get_current_location()

    # Combine contexts
    ctx = {
        "date": time_ctx["date"],
        "timezone_name": time_ctx["timezone_name"],
        "utc_offset": time_ctx["utc_offset"],
    }

    # Add location data if available
    if location_ctx.get("status") == "success":
        ctx.update(
            {
                "city": location_ctx.get("city", ""),
                "region": location_ctx.get("region", ""),
                "country": location_ctx.get("country", ""),
                "lat": location_ctx.get("lat", 0.0),
                "lon": location_ctx.get("lon", 0.0),
                "timezone": location_ctx.get("timezone", ""),
            }
        )

    return ctx


@mcp.resource("geo://location")
def get_location_resource() -> str:
    """Get formatted location information as a readable string."""
    ctx = get_full_context()
    return format_context(ctx)


@mcp.resource("geo://time")
def get_time_resource() -> str:
    """Get formatted time information as a readable string."""
    ctx = get_current_time()
    return f"""
Current date: {datetime.datetime.fromisoformat(ctx["date"]).strftime("%A, %B %d, %Y, %I:%M %p")}
Timezone: {ctx["timezone_name"]} (UTC{ctx["utc_offset"]})
"""


@mcp.prompt()
def location_aware_task(task: str) -> str:
    """Generate a location-aware task prompt.

    This prompt includes current location and time context for tasks
    that might benefit from geographic awareness.
    """
    ctx = get_full_context()
    return f"""
# Role
You are a location-aware assistant with current environmental context.

# Current Context
{format_context(ctx)}

# Task
{task}

# Instructions
- Consider the current location and time in your response
- Adjust recommendations based on timezone and geographic context
- Be aware of any location-specific constraints or considerations
"""


def _format_utc_offset(dt: datetime.datetime) -> str:
    """Return UTC offset string like '+02:00' or '-05:00'."""
    offset = dt.utcoffset()
    if offset is None:
        offset = datetime.datetime.now(datetime.UTC).astimezone().utcoffset()
    if offset is None:
        return "+00:00"
    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def format_context(ctx: dict[str, Any]) -> str:
    """Format context dict as a human-readable block."""
    now = datetime.datetime.fromisoformat(ctx["date"])
    lines = [
        f"Current date: {now.strftime('%A, %B %d, %Y, %I:%M %p')}",
        f"Timezone: {ctx['timezone_name']} (UTC{ctx['utc_offset']})",
    ]

    if "city" in ctx:
        location_parts = [ctx["city"]]
        if ctx.get("region") and ctx["region"] != ctx["city"]:
            location_parts.append(ctx["region"])
        if ctx.get("country"):
            location_parts.append(ctx["country"])
        coords = ""
        if ctx.get("lat") is not None and ctx.get("lon") is not None:
            coords = f" ({ctx['lat']:.2f}°N, {ctx['lon']:.2f}°E)"
        lines.append(f"Location: {', '.join(location_parts)}{coords}")

    return "\n".join(lines)

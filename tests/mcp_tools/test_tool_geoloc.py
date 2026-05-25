import datetime
import json
from unittest.mock import patch, MagicMock


from minia_mcp_server.tool_geoloc import (
    get_current_location,
    get_current_time,
    get_full_context,
    format_context,
    _format_utc_offset,
)


class TestGetCurrentLocation:
    def test_location_success(self):
        mock_resp = {
            "status": "success",
            "city": "Paris",
            "regionName": "Ile-de-France",
            "country": "FR",
            "lat": 48.85,
            "lon": 2.35,
            "timezone": "Europe/Paris",
        }
        mock_urlopen = MagicMock()
        mock_urlopen.read.return_value = json.dumps(mock_resp).encode()
        mock_urlopen.__enter__ = MagicMock(return_value=mock_urlopen)
        mock_urlopen.__exit__ = MagicMock(return_value=False)

        with patch("minia_mcp_server.tool_geoloc.urllib.request.urlopen") as mock:
            mock.return_value = mock_urlopen
            result = get_current_location()
            assert result["status"] == "success"
            assert result["city"] == "Paris"
            assert result["country"] == "FR"

    def test_location_unsuccessful_status(self):
        mock_resp = {"status": "fail", "message": "bad"}
        mock_urlopen = MagicMock()
        mock_urlopen.read.return_value = json.dumps(mock_resp).encode()
        mock_urlopen.__enter__ = MagicMock(return_value=mock_urlopen)
        mock_urlopen.__exit__ = MagicMock(return_value=False)

        with patch("minia_mcp_server.tool_geoloc.urllib.request.urlopen") as mock:
            mock.return_value = mock_urlopen
            result = get_current_location()
            assert result["status"] == "fail"
            assert "error" in result

    def test_location_network_error(self):
        with patch("minia_mcp_server.tool_geoloc.urllib.request.urlopen") as mock:
            mock.side_effect = Exception("network down")
            result = get_current_location()
            assert result["status"] == "error"
            assert "network" in result["error"].lower()


class TestGetCurrentTime:
    def test_returns_time_dict(self):
        result = get_current_time()
        assert "date" in result
        assert "timezone_name" in result
        assert "utc_offset" in result

    def test_date_is_valid_iso(self):
        result = get_current_time()
        dt = datetime.datetime.fromisoformat(result["date"])
        assert isinstance(dt, datetime.datetime)

    def test_utc_offset_format(self):
        result = get_current_time()
        offset = result["utc_offset"]
        assert len(offset) == 6  # +HH:MM or -HH:MM
        assert offset[0] in ("+", "-")
        assert offset[3] == ":"


class TestGetFullContext:
    def test_returns_combined(self):
        result = get_full_context()
        assert "date" in result
        assert "timezone_name" in result
        assert "utc_offset" in result

    def test_includes_location_on_success(self):
        with patch("minia_mcp_server.tool_geoloc.get_current_location") as mock_loc:
            mock_loc.return_value = {
                "status": "success",
                "city": "Berlin",
                "region": "Berlin",
                "country": "DE",
                "lat": 52.5,
                "lon": 13.4,
                "timezone": "Europe/Berlin",
            }
            result = get_full_context()
            assert result["city"] == "Berlin"
            assert result["country"] == "DE"

    def test_excludes_location_on_failure(self):
        with patch("minia_mcp_server.tool_geoloc.get_current_location") as mock_loc:
            mock_loc.return_value = {"status": "error", "error": "fail"}
            result = get_full_context()
            assert "city" not in result


class TestFormatContext:
    def test_basic_format(self):
        ctx = {
            "date": "2025-06-15T14:30:00+02:00",
            "timezone_name": "Europe/Paris",
            "utc_offset": "+02:00",
        }
        result = format_context(ctx)
        assert "2025" in result
        assert "Europe/Paris" in result
        assert "+02:00" in result

    def test_format_with_location(self):
        ctx = {
            "date": "2025-06-15T14:30:00+02:00",
            "timezone_name": "Europe/Paris",
            "utc_offset": "+02:00",
            "city": "Lyon",
            "region": "Auvergne-Rhone-Alpes",
            "country": "FR",
            "lat": 45.76,
            "lon": 4.83,
        }
        result = format_context(ctx)
        assert "Lyon" in result
        assert "45.76°N" in result
        assert "4.83°E" in result


class TestFormatUtcOffset:
    def test_positive_offset(self):
        dt = datetime.datetime(
            2025, 6, 15, tzinfo=datetime.timezone(datetime.timedelta(hours=2))
        )
        result = _format_utc_offset(dt)
        assert result == "+02:00"

    def test_negative_offset(self):
        dt = datetime.datetime(
            2025, 6, 15, tzinfo=datetime.timezone(datetime.timedelta(hours=-5))
        )
        result = _format_utc_offset(dt)
        assert result == "-05:00"

    def test_zero_offset(self):
        dt = datetime.datetime(2025, 6, 15, tzinfo=datetime.timezone.utc)
        result = _format_utc_offset(dt)
        assert result == "+00:00"

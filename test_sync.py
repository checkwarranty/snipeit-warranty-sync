#!/usr/bin/env python3
"""
Unit tests for Snipe-IT sync script.
Tests brand detection, date formatting, API mapping, and dry-run execution.
"""

import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Ensure sync can be imported
sys.path.insert(0, os.path.dirname(__file__))

from sync import (
    detect_brand,
    format_iso_to_date,
    calculate_warranty_months,
    extract_snipe_date,
    SnipeItClient,
    CheckWarrantyClient,
    run_sync,
)
import argparse


class TestSnipeItSync(unittest.TestCase):

    def test_detect_brand_by_model(self):
        self.assertEqual(detect_brand("UNKNOWN123", "Dell Latitude 5420"), "dell")
        self.assertEqual(detect_brand("UNKNOWN123", "ThinkPad T14 Gen 2"), "lenovo")
        self.assertEqual(detect_brand("UNKNOWN123", "HP EliteBook 840 G8"), "hp")
        self.assertEqual(detect_brand("UNKNOWN123", "Hewlett-Packard ProBook"), "hp")
        self.assertEqual(detect_brand("UNKNOWN123", "MacBook Pro 16"), "apple")

    def test_detect_brand_avoids_substring_false_positives(self):
        # "Sharp Display" should not falsely match "hp"
        self.assertIsNone(detect_brand("UNKNOWN123", "Sharp Aquos Monitor"))

    def test_detect_brand_by_serial_syntax(self):
        self.assertEqual(detect_brand("8HG76F2"), "dell")  # 7-char alphanumeric
        self.assertEqual(detect_brand("PF4A1234"), "lenovo")  # 8-char alphanumeric
        self.assertEqual(detect_brand("5CG1234567"), "hp")  # 10-char HP prefix
        self.assertEqual(detect_brand("C02G12345678"), "apple")  # 12-char Apple prefix

    def test_format_iso_to_date(self):
        self.assertEqual(format_iso_to_date("2026-04-11T23:59:59.000Z"), "2026-04-11")
        self.assertEqual(format_iso_to_date("2024-12-01"), "2024-12-01")
        self.assertIsNone(format_iso_to_date(None))
        self.assertIsNone(format_iso_to_date("invalid-date"))

    def test_calculate_warranty_months(self):
        # 36 months (3 years)
        self.assertEqual(calculate_warranty_months("2023-01-01", "2026-01-01"), 36)
        # 12 months (1 year)
        self.assertEqual(calculate_warranty_months("2024-05-15", "2025-05-15"), 12)
        # 6 months
        self.assertEqual(calculate_warranty_months("2024-01-01", "2024-07-01"), 6)
        # Same date
        self.assertEqual(calculate_warranty_months("2024-01-01", "2024-01-01"), 0)
        # Invalid / missing dates
        self.assertIsNone(calculate_warranty_months(None, "2024-01-01"))
        self.assertIsNone(calculate_warranty_months("bad-date", "2024-01-01"))

    def test_extract_snipe_date(self):
        self.assertEqual(extract_snipe_date({"date": "2026-04-11"}), "2026-04-11")
        self.assertEqual(extract_snipe_date("2026-04-11"), "2026-04-11")
        self.assertIsNone(extract_snipe_date(None))
        self.assertIsNone(extract_snipe_date({}))

    @patch("sync.SnipeItClient._request")
    def test_snipeit_get_assets_pagination(self, mock_request):
        # Simulate 2 pages of assets
        mock_request.side_effect = [
            {"rows": [{"id": 1, "serial": "PF4TEST1"}, {"id": 2, "serial": "PF4TEST2"}]},
            {"rows": [{"id": 3, "serial": "PF4TEST3"}]},
        ]

        client = SnipeItClient("https://assets.example.com", "token123")
        assets = client.get_hardware_assets(total_limit=3, page_size=2)

        self.assertEqual(len(assets), 3)
        self.assertEqual(assets[0]["serial"], "PF4TEST1")
        self.assertEqual(assets[2]["serial"], "PF4TEST3")
        self.assertEqual(mock_request.call_count, 2)

    @patch("sync.SnipeItClient._request")
    def test_snipeit_update_asset_handles_error_status(self, mock_request):
        client = SnipeItClient("https://assets.example.com", "token123")

        # HTTP 200 with error payload (Snipe-IT pattern)
        mock_request.return_value = {"status": "error", "messages": "Asset tag already exists"}
        success = client.update_asset(10, {"warranty_months": 12})
        self.assertFalse(success)

        # HTTP 200 with success
        mock_request.return_value = {"status": "success", "messages": "Asset updated"}
        success = client.update_asset(10, {"warranty_months": 12})
        self.assertTrue(success)

    @patch("sync.CheckWarrantyClient._request")
    def test_checkwarranty_lookup_success(self, mock_request):
        mock_request.return_value = {
            "status": "completed",
            "warranty": {
                "status": "active",
                "endDate": "2026-05-15T00:00:00.000Z",
                "details": {
                    "processor": "Intel Core i7-1260P",
                    "memory": "16GB DDR4",
                    "hardDrive": "512GB SSD"
                }
            }
        }

        cw = CheckWarrantyClient("https://checkwarranty.info/api/v1", "cw_live_test")
        result = cw.lookup_device("PF4TEST", "lenovo")

        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["warranty"]["details"]["processor"], "Intel Core i7-1260P")

    @patch.dict(os.environ, {
        "SNIPEIT_URL": "https://assets.example.com",
        "SNIPEIT_API_TOKEN": "token123",
        "CHECKWARRANTY_API_KEY": "cw_live_123",
        "FIELD_CPU": "_snipeit_cpu_1",
        "FIELD_WARRANTY_EXPIRATION": "_snipeit_warranty_exp_5",
    })
    @patch("sync.SnipeItClient")
    @patch("sync.CheckWarrantyClient")
    def test_run_sync_execution(self, mock_cw_cls, mock_snipe_cls):
        mock_snipe = MagicMock()
        mock_snipe_cls.return_value = mock_snipe
        mock_snipe.get_hardware_assets.return_value = [
            {
                "id": 101,
                "serial": "8HG76F2",
                "model": {"name": "Dell Latitude 5420"},
                "warranty_expires": None,
                "purchase_date": None,
            }
        ]

        mock_cw = MagicMock()
        mock_cw_cls.return_value = mock_cw
        mock_cw.lookup_device.return_value = {
            "status": "completed",
            "warranty": {
                "startDate": "2023-01-01T00:00:00.000Z",
                "endDate": "2026-01-01T00:00:00.000Z",
                "details": {"processor": "Intel Core i5-1145G7"}
            }
        }
        mock_snipe.update_asset.return_value = True

        args = argparse.Namespace(dry_run=False, limit=10, brand=None, force=False, verbose=False)
        run_sync(args)

        mock_snipe.update_asset.assert_called_once()
        call_id, payload = mock_snipe.update_asset.call_args[0]
        self.assertEqual(call_id, 101)
        self.assertEqual(payload["purchase_date"], "2023-01-01")
        self.assertEqual(payload["warranty_months"], 36)
        self.assertEqual(payload["_snipeit_warranty_exp_5"], "2026-01-01")
        self.assertEqual(payload["_snipeit_cpu_1"], "Intel Core i5-1145G7")


if __name__ == "__main__":
    unittest.main()

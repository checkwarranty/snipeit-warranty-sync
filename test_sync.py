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

from sync import detect_brand, format_iso_to_date, SnipeItClient, CheckWarrantyClient, run_sync
import argparse


class TestSnipeItSync(unittest.TestCase):

    def test_detect_brand_by_model(self):
        self.assertEqual(detect_brand("UNKNOWN123", "Dell Latitude 5420"), "dell")
        self.assertEqual(detect_brand("UNKNOWN123", "ThinkPad T14 Gen 2"), "lenovo")
        self.assertEqual(detect_brand("UNKNOWN123", "HP EliteBook 840 G8"), "hp")
        self.assertEqual(detect_brand("UNKNOWN123", "MacBook Pro 16"), "apple")

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

    @patch("sync.SnipeItClient._request")
    def test_snipeit_get_assets(self, mock_request):
        mock_request.return_value = {"rows": [{"id": 1, "serial": "PF4TEST"}]}

        client = SnipeItClient("https://assets.example.com", "token123")
        assets = client.get_hardware_assets(limit=10)

        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["serial"], "PF4TEST")
        mock_request.assert_called_once()

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
        "FIELD_CPU": "_snipeit_cpu_1"
    })
    @patch("sync.SnipeItClient")
    @patch("sync.CheckWarrantyClient")
    def test_run_sync_dry_run(self, mock_cw_cls, mock_snipe_cls):
        mock_snipe = MagicMock()
        mock_snipe_cls.return_value = mock_snipe
        mock_snipe.get_hardware_assets.return_value = [
            {
                "id": 101,
                "serial": "8HG76F2",
                "model": {"name": "Dell Latitude 5420"},
                "warranty_expires": None
            }
        ]

        mock_cw = MagicMock()
        mock_cw_cls.return_value = mock_cw
        mock_cw.lookup_device.return_value = {
            "status": "completed",
            "warranty": {
                "endDate": "2025-10-01T00:00:00.000Z",
                "details": {"processor": "Intel Core i5-1145G7"}
            }
        }

        args = argparse.Namespace(dry_run=True, limit=10, brand=None, force=False, verbose=False)
        run_sync(args)

        # In dry run, update_asset should NOT be called
        mock_snipe.update_asset.assert_not_called()


if __name__ == "__main__":
    unittest.main()

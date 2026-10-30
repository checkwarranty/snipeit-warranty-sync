import unittest
from unittest.mock import patch
import sync

class ContractTests(unittest.TestCase):
    def test_real_api_specs_only_result(self):
        warranty, specs = sync.extract_result({"status": "completed", "warranty": {"status": "unknown", "details": {"processor": "Xeon", "memory": "16 GB"}}})
        self.assertEqual(specs, {"cpu": "Xeon", "ram": "16 GB"})

    def test_errors_and_not_found_do_not_become_success(self):
        for value in ({"status":"failed"}, {"status":"pending"}, {"status":"completed","warranty":{"status":"not_found","details":{"message":"missing"}}}, None):
            self.assertEqual(sync.extract_result(value), ({}, {}))

    def test_async_partial_returns_completed_item(self):
        client = sync.CheckWarrantyClient("https://checkwarranty.info/api/v1", "sandbox")
        item = {"status":"completed","warranty":{"endDate":"2027-01-01"}}
        with patch.object(client, "_request", return_value={"status":"partial","items":[item]}), patch.object(sync.time, "sleep"):
            self.assertEqual(client._poll_batch_result("batch", max_retries=1), item)

    def test_malformed_date_is_ignored(self):
        self.assertIsNone(sync.format_iso_to_date({"bad":"date"}))

    def test_purchase_date_never_comes_from_warranty_start(self):
        payload = sync.build_asset_payload({"startDate":"2024-01-01","endDate":"2027-01-01"},{},{"purchase_date":None},{"warranty_exp":"expiry"})
        self.assertNotIn("purchase_date",payload)
        self.assertNotIn("warranty_months",payload)
        self.assertEqual(payload["expiry"],"2027-01-01")

    def test_inexact_native_months_are_not_written(self):
        payload=sync.build_asset_payload({"endDate":"2027-01-05"},{},{"purchase_date":"2024-01-01"},{"warranty_exp":"expiry"})
        self.assertNotIn("warranty_months",payload)

#!/usr/bin/env python3
"""
CheckWarranty - Snipe-IT Hardware Warranty & Factory Specs Synchronizer
Syncs warranty expiration dates and factory BOM specifications into Snipe-IT ITAM.
Zero external dependencies required (uses standard library urllib/json).
"""

import os
import sys
import argparse
import logging
import time
import uuid
import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime
import urllib.request
import urllib.error

# Attempt to load .env if python-dotenv is available, otherwise read OS environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("checkwarranty-sync")


def detect_brand(serial: str, model_name: str = "") -> Optional[str]:
    """Infer manufacturer from serial number syntax or model name."""
    s_upper = (serial or "").strip().upper()
    m_lower = (model_name or "").strip().lower()

    if any(k in m_lower for k in ("dell", "latitude", "optiplex", "precision", "vostro", "xps")):
        return "dell"
    if any(k in m_lower for k in ("lenovo", "thinkpad", "thinkcentre", "ideapad", "thinkstation")):
        return "lenovo"
    if any(k in m_lower for k in ("hp", "elitebook", "probook", "zbook", "compaq")):
        return "hp"
    if any(k in m_lower for k in ("apple", "macbook", "imac", "mac mini", "mac studio")):
        return "apple"

    # Syntax heuristics
    if len(s_upper) == 7 and s_upper.isalnum():
        return "dell"
    if len(s_upper) == 8 and s_upper.isalnum():
        return "lenovo"
    if len(s_upper) == 10 and (s_upper.startswith("5CG") or s_upper.startswith("5CD") or s_upper.startswith("CND")):
        return "hp"
    if len(s_upper) == 12 and s_upper.startswith("C02"):
        return "apple"

    return None


class SnipeItClient:
    """Handles communication with the Snipe-IT REST API using urllib."""

    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "CheckWarranty-SnipeIT-Sync/1.0",
        }

    def _request(self, method: str, url: str, data: Optional[Dict[str, Any]] = None) -> Any:
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res_body = resp.read().decode("utf-8")
                return json.loads(res_body) if res_body else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else ""
            logger.error(f"Snipe-IT HTTP {e.code} error on {method} {url}: {err_body}")
            raise
        except urllib.error.URLError as e:
            logger.error(f"Snipe-IT connection error: {e}")
            raise

    def get_hardware_assets(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Fetch a page of hardware assets from Snipe-IT."""
        url = f"{self.base_url}/api/v1/hardware?limit={limit}&offset={offset}&sort=id&order=asc"
        res = self._request("GET", url)
        return res.get("rows", [])

    def update_asset(self, asset_id: int, payload: Dict[str, Any]) -> bool:
        """Update an existing asset in Snipe-IT."""
        url = f"{self.base_url}/api/v1/hardware/{asset_id}"
        try:
            self._request("PATCH", url, payload)
            return True
        except Exception as e:
            logger.error(f"Failed to update Snipe-IT asset #{asset_id}: {e}")
            return False


class CheckWarrantyClient:
    """Handles communication with the CheckWarranty B2B REST API using urllib."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "X-API-Key": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "CheckWarranty-SnipeIT-Sync/1.0",
        }

    def _request(self, method: str, path: str, data: Optional[Dict[str, Any]] = None, extra_headers: Optional[Dict[str, str]] = None) -> Any:
        url = f"{self.base_url}{path}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        headers = dict(self.headers)
        if extra_headers:
            headers.update(extra_headers)

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                res_body = resp.read().decode("utf-8")
                return json.loads(res_body) if res_body else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8") if e.fp else ""
            if e.code == 404:
                return None
            if e.code == 402:
                logger.error("CheckWarranty credit balance exhausted (HTTP 402). Top up credits at checkwarranty.info/dashboard/billing")
                sys.exit(2)
            logger.warning(f"CheckWarranty HTTP {e.code} for {path}: {err_body}")
            return None
        except urllib.error.URLError as e:
            logger.error(f"CheckWarranty connection error: {e}")
            return None

    def lookup_device(self, serial: str, brand: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Query CheckWarranty for a single serial number."""
        idempotency_key = str(uuid.uuid4())
        extra = {"Idempotency-Key": idempotency_key}

        if brand:
            payload = {"serialNumber": serial, "brand": brand}
            res = self._request("POST", "/devices/lookup", payload, extra_headers=extra)
        else:
            payload = {"serialNumber": serial}
            res = self._request("POST", "/devices/auto-detect", payload, extra_headers=extra)

        if not res:
            return None

        # Handle async 202 accepted response if vendor scraper takes longer
        if res.get("status") == "in_progress" or res.get("status") == "pending":
            batch_id = res.get("batchId")
            if batch_id:
                return self._poll_batch_result(batch_id)

        return res

    def _poll_batch_result(self, batch_id: str, max_retries: int = 6) -> Optional[Dict[str, Any]]:
        """Poll batch status endpoint if scan returned 202 Accepted."""
        for attempt in range(max_retries):
            time.sleep(4)
            res = self._request("GET", f"/devices/scans/{batch_id}")
            if res and res.get("status") == "completed":
                items = res.get("items", [])
                return items[0] if items else res
        return None


def format_iso_to_date(iso_str: Optional[str]) -> Optional[str]:
    """Convert ISO 8601 timestamp string to YYYY-MM-DD for Snipe-IT."""
    if not iso_str:
        return None
    try:
        clean = iso_str.split("T")[0]
        # Validate format
        datetime.strptime(clean, "%Y-%m-%d")
        return clean
    except ValueError:
        return None


def run_sync(args: argparse.Namespace) -> None:
    snipeit_url = os.getenv("SNIPEIT_URL")
    snipeit_token = os.getenv("SNIPEIT_API_TOKEN")
    cw_key = os.getenv("CHECKWARRANTY_API_KEY")
    cw_url = os.getenv("CHECKWARRANTY_API_URL", "https://checkwarranty.info/api/v1")

    if not snipeit_url or not snipeit_token:
        logger.error("Missing SNIPEIT_URL or SNIPEIT_API_TOKEN in environment variables.")
        sys.exit(1)
    if not cw_key:
        logger.error("Missing CHECKWARRANTY_API_KEY in environment variables.")
        sys.exit(1)

    snipe = SnipeItClient(snipeit_url, snipeit_token)
    cw = CheckWarrantyClient(cw_url, cw_key)

    custom_fields = {
        "cpu": os.getenv("FIELD_CPU", "").strip(),
        "ram": os.getenv("FIELD_RAM", "").strip(),
        "storage": os.getenv("FIELD_STORAGE", "").strip(),
        "display": os.getenv("FIELD_DISPLAY", "").strip(),
    }

    logger.info(f"Starting Snipe-IT Sync (dry_run={args.dry_run}, limit={args.limit}, force={args.force})")

    assets = snipe.get_hardware_assets(limit=args.limit)
    logger.info(f"Fetched {len(assets)} hardware assets from Snipe-IT.")

    stats = {"processed": 0, "updated": 0, "skipped": 0, "not_found": 0, "errors": 0}

    for asset in assets:
        asset_id = asset.get("id")
        serial = (asset.get("serial") or "").strip()
        model_name = (asset.get("model", {}).get("name") or "") if isinstance(asset.get("model"), dict) else ""
        existing_warranty = asset.get("warranty_expires", {}).get("date") if isinstance(asset.get("warranty_expires"), dict) else None

        if not serial:
            stats["skipped"] += 1
            continue

        if existing_warranty and not args.force:
            if args.verbose:
                logger.info(f"Skipping asset #{asset_id} ({serial}) - warranty already set: {existing_warranty}")
            stats["skipped"] += 1
            continue

        brand = args.brand or detect_brand(serial, model_name)
        stats["processed"] += 1

        logger.info(f"Querying CheckWarranty: #{asset_id} [Serial: {serial}, Brand: {brand or 'auto-detect'}]...")
        result = cw.lookup_device(serial, brand)

        if not result or result.get("status") == "not_found":
            logger.info(f"No warranty record found for serial {serial}")
            stats["not_found"] += 1
            continue

        warranty_data = result.get("warranty", {}) or {}
        details = warranty_data.get("details", {}) or {}

        end_date = format_iso_to_date(warranty_data.get("endDate"))
        start_date = format_iso_to_date(warranty_data.get("startDate"))

        update_payload: Dict[str, Any] = {}

        if end_date:
            update_payload["warranty_expires"] = end_date
        if start_date and not asset.get("purchase_date"):
            update_payload["purchase_date"] = start_date

        # Enrich custom specs if configured in .env
        if custom_fields["cpu"] and details.get("processor"):
            update_payload[custom_fields["cpu"]] = details["processor"]
        if custom_fields["ram"] and details.get("memory"):
            update_payload[custom_fields["ram"]] = details["memory"]
        if custom_fields["storage"] and details.get("hardDrive"):
            update_payload[custom_fields["storage"]] = details["hardDrive"]
        if custom_fields["display"] and details.get("display"):
            update_payload[custom_fields["display"]] = details["display"]

        if not update_payload:
            stats["skipped"] += 1
            continue

        if args.dry_run:
            logger.info(f"[DRY RUN] Would update asset #{asset_id} ({serial}) with: {update_payload}")
            stats["updated"] += 1
        else:
            success = snipe.update_asset(asset_id, update_payload)
            if success:
                logger.info(f"Successfully updated asset #{asset_id} ({serial}) -> Warranty: {end_date}")
                stats["updated"] += 1
            else:
                stats["errors"] += 1

        # Courteous pacing
        time.sleep(0.3)

    logger.info("=" * 50)
    logger.info("Sync Execution Complete!")
    logger.info(f"Summary: {stats}")
    logger.info("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="Sync CheckWarranty data into Snipe-IT ITAM")
    parser.add_argument("--dry-run", action="store_true", help="Preview updates without modifying Snipe-IT")
    parser.add_argument("--limit", type=int, default=100, help="Max number of assets to inspect (default: 100)")
    parser.add_argument("--brand", choices=["dell", "lenovo", "hp", "apple"], help="Filter by specific manufacturer brand")
    parser.add_argument("--force", action="store_true", help="Re-sync assets that already have warranty dates")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    run_sync(args)


if __name__ == "__main__":
    main()

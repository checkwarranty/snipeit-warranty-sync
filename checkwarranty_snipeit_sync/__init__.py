#!/usr/bin/env python3
"""
CheckWarranty - Snipe-IT Hardware Warranty & Factory Specs Synchronizer
Syncs warranty expiration dates and factory BOM specifications into Snipe-IT ITAM.
Zero external dependencies required (uses standard library urllib/json).
"""

import os
import calendar
import sys
import argparse
import logging
import time
import uuid
import json
import re
from typing import Dict, Any, List, Optional
from datetime import date, datetime
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
    if re.search(r"\b(hp|hewlett[\s-]packard|elitebook|probook|zbook|compaq)\b", m_lower):
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


def calculate_warranty_months(start_date_str: Optional[str], end_date_str: Optional[str]) -> Optional[int]:
    """
    Calculate warranty duration in months between start and end dates.
    Snipe-IT computes warranty expiration dynamically from purchase_date + warranty_months.
    """
    if not start_date_str or not end_date_str:
        return None
    try:
        d1 = datetime.strptime(start_date_str, "%Y-%m-%d")
        d2 = datetime.strptime(end_date_str, "%Y-%m-%d")
        if d2 <= d1:
            return 0
        diff_days = (d2 - d1).days
        months = round(diff_days / 30.4375)
        return max(1, months)
    except ValueError:
        return None


def extract_snipe_date(val: Any) -> Optional[str]:
    """Safely extract date string from Snipe-IT API format (string or dict)."""
    if isinstance(val, dict):
        d = val.get("date")
        return d.strip() if isinstance(d, str) and d.strip() else None
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


class SnipeItClient:
    """Handles communication with the Snipe-IT REST API using urllib."""

    def __init__(self, base_url: str, api_token: str):
        self.base_url = (base_url or "").strip().rstrip("/")
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

    def get_hardware_assets(self, total_limit: int = 100, page_size: int = 50) -> List[Dict[str, Any]]:
        """Fetch hardware assets from Snipe-IT with automatic pagination up to total_limit."""
        all_assets: List[Dict[str, Any]] = []
        offset = 0

        while len(all_assets) < total_limit:
            fetch_count = min(page_size, total_limit - len(all_assets))
            url = f"{self.base_url}/api/v1/hardware?limit={fetch_count}&offset={offset}&sort=id&order=asc"
            res = self._request("GET", url)
            rows = res.get("rows", [])
            if not rows:
                break
            all_assets.extend(rows)
            offset += len(rows)
            if len(rows) < fetch_count:
                break

        return all_assets

    def update_asset(self, asset_id: int, payload: Dict[str, Any]) -> bool:
        """Update an existing asset in Snipe-IT. Handles validation errors returned with HTTP 200."""
        url = f"{self.base_url}/api/v1/hardware/{asset_id}"
        try:
            res = self._request("PATCH", url, payload)
            if isinstance(res, dict) and res.get("status") == "error":
                logger.error(f"Snipe-IT rejected update for asset #{asset_id}: {res.get('messages')}")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to update Snipe-IT asset #{asset_id}: {e}")
            return False


class CheckWarrantyClient:
    """Handles communication with the CheckWarranty B2B REST API using urllib."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = (base_url or "").strip().rstrip("/")
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
            if not res:
                continue
            status = res.get("status")
            if status in ("completed", "partial"):
                items = res.get("items", [])
                return items[0] if items and isinstance(items[0], dict) else None
            if status in ("failed", "error", "not_found"):
                logger.warning(f"CheckWarranty async scan ended with status: {status}")
                return res
        return None


def format_iso_to_date(iso_str: Optional[str]) -> Optional[str]:
    """Convert ISO 8601 timestamp string to YYYY-MM-DD for Snipe-IT."""
    if not isinstance(iso_str, str) or not iso_str:
        return None
    try:
        clean = iso_str.split("T")[0]
        # Validate format
        datetime.strptime(clean, "%Y-%m-%d")
        return clean
    except ValueError:
        return None



def extract_result(result):
    """Read the public B2B DTO, including specs-only completed results."""
    if not isinstance(result, dict) or result.get("status") not in (None, "completed"):
        return {}, {}
    warranty = result.get("warranty")
    if not isinstance(warranty, dict):
        return {}, {}
    details = warranty.get("details") or {}
    if not isinstance(details, dict):
        details = {}
    specs = {}
    for source, target in (("processor", "cpu"), ("memory", "ram"), ("hardDrive", "storage"), ("display", "display")):
        value = details.get(source)
        if isinstance(value, str) and value.strip().lower() not in ("", "unknown", "n/a", "none", "not found", "-"):
            specs[target] = value.strip()
    device = result.get("device") or {}
    if isinstance(device, dict) and warranty.get("status") != "not_found":
        for source, target in (("model", "model"), ("productNumber", "product_number"), ("description", "description")):
            value = device.get(source)
            if isinstance(value, str) and value.strip() and not re.match(r"^(unknown( device)?|[a-z]+ device|n/a|none|-)$", value.strip(), re.I):
                specs[target] = value.strip()
    if warranty.get("status") == "not_found" and not specs:
        return {}, {}
    return warranty, specs


def exact_warranty_months(start, end):
    """Return whole calendar months only when the interval matches exactly."""
    start, end = format_iso_to_date(start), format_iso_to_date(end)
    if not start or not end:
        return None
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    months = (last.year - first.year) * 12 + last.month - first.month
    if months <= 0:
        return None
    day = min(first.day, calendar.monthrange(last.year, last.month)[1])
    return months if last.day == day else None



def build_asset_payload(warranty, specs, asset, custom_fields):
    """Never infer purchase_date from warranty/manufacture dates."""
    payload = {}
    end = format_iso_to_date(warranty.get("endDate"))
    purchase = extract_snipe_date(asset.get("purchase_date"))
    months = exact_warranty_months(purchase, end)
    if months:
        payload["warranty_months"] = months
    if end and custom_fields.get("warranty_exp"):
        payload[custom_fields["warranty_exp"]] = end
    for key in ("cpu", "ram", "storage", "display"):
        if custom_fields.get(key) and specs.get(key):
            payload[custom_fields[key]] = specs[key]
    return payload


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
        "warranty_exp": os.getenv("FIELD_WARRANTY_EXPIRATION", "").strip(),
    }

    if args.limit <= 0:
        logger.error("--limit must be greater than 0.")
        sys.exit(1)

    logger.info(f"Starting Snipe-IT Sync (dry_run={args.dry_run}, limit={args.limit}, force={args.force})")

    assets = snipe.get_hardware_assets(total_limit=args.limit)
    logger.info(f"Fetched {len(assets)} hardware assets from Snipe-IT.")

    stats = {"processed": 0, "updated": 0, "skipped": 0, "not_found": 0, "errors": 0}

    for asset in assets:
        asset_id = asset.get("id")
        serial = (asset.get("serial") or "").strip()
        model_name = (asset.get("model", {}).get("name") or "") if isinstance(asset.get("model"), dict) else ""
        existing_warranty = extract_snipe_date(asset.get("warranty_expires"))
        existing_purchase = extract_snipe_date(asset.get("purchase_date"))

        if not asset_id or not serial:
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
        if getattr(args, "plan", False):
            logger.info("[PLAN] Lookup required; no CheckWarranty request sent")
            stats["skipped"] += 1
            continue
        result = cw.lookup_device(serial, brand)

        if not result or result.get("status") == "not_found":
            logger.info(f"No warranty record found for serial {serial}")
            stats["not_found"] += 1
            continue

        warranty_data, specs = extract_result(result)
        update_payload = build_asset_payload(warranty_data, specs, asset, custom_fields)

        if not update_payload:
            stats["skipped"] += 1
            continue

        if args.dry_run:
            logger.info(f"[DRY RUN] Would update asset #{asset_id} ({serial}) with: {update_payload}")
            stats["updated"] += 1
        else:
            success = snipe.update_asset(asset_id, update_payload)
            if success:
                logger.info(f"Successfully updated asset #{asset_id} ({serial}) -> Payload: {update_payload}")
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

    parser.add_argument("--plan", action="store_true", help="List assets needing lookup without calling CheckWarranty or writing changes.")
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    run_sync(args)


if __name__ == "__main__":
    main()

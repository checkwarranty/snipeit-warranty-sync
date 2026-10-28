# CheckWarranty &bull; Snipe-IT Asset Sync

Automate hardware warranty tracking and factory hardware specification enrichment in [Snipe-IT](https://snipeitapp.com/) using the [CheckWarranty API](https://checkwarranty.info/docs/api).

![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python: 3.8+](https://img.shields.io/badge/Python-3.8%2B-green.svg)
![Integration: Snipe--IT](https://img.shields.io/badge/ITAM-Snipe--IT-orange.svg)

---

## Overview

Most enterprise IT teams and refurbishers maintain serial numbers in Snipe-IT, but warranty expiration dates and factory hardware specifications (CPU, RAM, SSD capacity) remain blank or outdated.

**`checkwarranty-snipeit-sync`** automatically:
1. Scans Snipe-IT for laptops, desktops, and workstations (Dell, Lenovo, HP, Apple).
2. Queries the official CheckWarranty B2B REST API for warranty coverage and factory component configurations.
3. Automatically updates Snipe-IT asset records:
   - **Warranty Expiration Date** and coverage duration.
   - **Purchase / Manufacture Date** (if available).
   - **Factory Specifications** (CPU model, RAM configuration, SSD capacity, display panel) mapped to your Snipe-IT custom fields.

---

## Workflow Diagram

```
┌─────────────────┐       1. Fetch assets       ┌────────────────────────┐
│  Snipe-IT ITAM  │ ◄─────────────────────────  │ checkwarranty-sync-cli │
│   (Self-hosted) │                             │      (Python 3)        │
└────────┬────────┘                             └───────────┬────────────┘
         │ 2. Return serial numbers                         │
         └─────────────────────────────────────────►        │ 3. Lookup warranty & specs
                                                            ▼
                                                ┌────────────────────────┐
                                                │   CheckWarranty API    │
                                                │ (Lenovo, Dell, HP, Mac)│
                                                └───────────┬────────────┘
         ┌────────────────┐ 5. Update asset fields          │
         │  Snipe-IT ITAM │ ◄───────────────────────────────┘ 4. Return verified data
         │   (Enriched)   │   (Warranty, CPU, RAM, SSD)
         └────────────────┘
```

---

## Quick Start (3 Minutes)

### 1. Clone & Install Dependencies

```bash
cd integrations/snipe-it
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```ini
# Snipe-IT Configuration
SNIPEIT_URL=https://assets.yourcompany.com
SNIPEIT_API_TOKEN=your_snipe_it_personal_access_token

# CheckWarranty Configuration (Get your key at https://checkwarranty.info/dashboard/api-keys)
CHECKWARRANTY_API_KEY=cw_live_your_api_key_here
CHECKWARRANTY_API_URL=https://checkwarranty.info/api/v1

# Sync Options
DRY_RUN=false
SYNC_SPECS=true
```

### 3. Run a Dry Run

Preview what assets would be updated without modifying your database:

```bash
python sync.py --dry-run
```

### 4. Execute Live Sync

```bash
python sync.py
```

---

## Command-Line Arguments

| Flag | Default | Description |
|---|---|---|
| `--dry-run` | `false` | Run without modifying Snipe-IT asset records. |
| `--limit <N>` | `100` | Maximum number of assets to process in one execution. |
| `--brand <name>` | all | Filter by specific brand (`dell`, `lenovo`, `hp`, `apple`). |
| `--force` | `false` | Re-check devices that already have warranty dates in Snipe-IT. |
| `--verbose` | `false` | Enable detailed debug output for HTTP requests. |

**Examples:**

```bash
# Check only Dell devices
python sync.py --brand dell --limit 50

# Re-scan all laptops including those with existing warranty dates
python sync.py --force --limit 200
```

---

## How Snipe-IT Warranty Calculation Works

In Snipe-IT, `warranty_expires` is a **dynamically calculated field** derived from `purchase_date` + `warranty_months`.
- The synchronizer automatically populates `purchase_date` (from manufacturer shipment / start date if blank in Snipe-IT).
- It calculates `warranty_months` between the start date and expiration date, updating Snipe-IT native warranty records.
- For manufacturers like Dell where start dates are optional, you can also map the exact expiration date directly to a custom date field via `FIELD_WARRANTY_EXPIRATION`.

---

## Custom Field Mapping (Optional)

If your Snipe-IT instance has custom fields configured for hardware components or expiration dates, map them in `.env`:

```ini
# Custom field DB column names from Snipe-IT (Settings -> Custom Fields)
FIELD_WARRANTY_EXPIRATION=_snipeit_warranty_exp_5
FIELD_CPU=_snipeit_cpu_1
FIELD_RAM=_snipeit_ram_2
FIELD_STORAGE=_snipeit_storage_3
FIELD_DISPLAY=_snipeit_screen_4
```

---

## Automated Scheduling

### Via Linux Cron (Daily at 2:00 AM)

```bash
0 2 * * * cd /opt/checkwarranty-snipeit-sync && .venv/bin/python sync.py >> /var/log/snipeit-warranty-sync.log 2>&1
```

### Via Docker

```bash
docker run --rm \
  -e SNIPEIT_URL="https://assets.company.com" \
  -e SNIPEIT_API_TOKEN="token" \
  -e CHECKWARRANTY_API_KEY="cw_live_..." \
  checkwarranty/snipeit-sync:latest
```

---

## License

MIT License. Designed and maintained by the CheckWarranty team.
For questions or API support, visit [CheckWarranty Documentation](https://checkwarranty.info/docs/api).

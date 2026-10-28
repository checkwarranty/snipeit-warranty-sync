Maintaining accurate warranty expiration dates and hardware specifications across hundreds or thousands of enterprise laptops is one of the most frustrating chores in IT Asset Management (ITAM). 

Most organizations running [Snipe-IT](https://snipeitapp.com/) have complete lists of serial numbers, but fields like warranty expiration date, purchase date, CPU model, and factory RAM/SSD capacity often remain blank.

In this guide, we will demonstrate how to automate warranty tracking and factory hardware enrichment in Snipe-IT using an open-source Python synchronizer.

---

## The Snipe-IT Warranty Architecture Challenge

In Snipe-IT, `warranty_expires` is not an independently writable database column. Instead, Snipe-IT dynamically calculates expiration dates using:

`warranty_expires = purchase_date + warranty_months`

If an API script attempts to send `{"warranty_expires": "2026-05-01"}`, Snipe-IT simply ignores the value. To update expiration dates properly via API, a synchronizer must:
1. Supply or preserve the asset's `purchase_date`.
2. Accurately calculate the integer difference in `warranty_months`.
3. Submit both fields so Snipe-IT renders the correct expiration date across all UI dashboards.

---

## How the Synchronizer Works

The open-source [checkwarranty/snipeit-warranty-sync](https://github.com/checkwarranty/snipeit-warranty-sync) tool operates with **zero external pip dependencies**, using Python 3 standard library:

- Queries Snipe-IT hardware API for assets missing warranty dates.
- Detects manufacturer (Dell, Lenovo, HP, Apple) via serial number syntax or model name.
- Queries CheckWarranty API to fetch confirmed warranty coverage and factory component configurations.
- Updates Snipe-IT asset records: sets `purchase_date` and `warranty_months`, and maps factory specs (CPU, RAM, SSD, display) to custom fields.

---

## Step-by-Step Setup

### Step 1: Clone and Configure

```bash
git clone https://github.com/checkwarranty/snipeit-warranty-sync.git
cd snipeit-warranty-sync
cp .env.example .env
```

Configure your environment credentials in `.env`:
```ini
SNIPEIT_URL=https://assets.yourcompany.com
SNIPEIT_API_TOKEN=your_snipe_it_personal_access_token
CHECKWARRANTY_API_KEY=cw_live_your_api_key

# Optional: Map factory specs to your Snipe-IT custom fields
FIELD_WARRANTY_EXPIRATION=_snipeit_warranty_exp_5
FIELD_CPU=_snipeit_cpu_1
FIELD_RAM=_snipeit_ram_2
FIELD_STORAGE=_snipeit_storage_3
```

### Step 2: Safe Dry-Run Simulation

Always verify what the script would change before updating your production database:

```bash
python sync.py --dry-run --limit 25
```

The output displays simulated payloads:
```text
[INFO] Querying CheckWarranty: #104 [Serial: 8HG76F2, Brand: dell]...
[INFO] [DRY RUN] Would update asset #104 (8HG76F2) with: {
  'purchase_date': '2023-01-15', 
  'warranty_months': 36, 
  '_snipeit_cpu_1': 'Intel Core i7-1185G7', 
  '_snipeit_ram_2': '16GB DDR4', 
  '_snipeit_storage_3': '512GB NVMe SSD'
}
```

### Step 3: Run via Docker or Cron

To run unattended via Docker Container:
```bash
docker run --rm \
  -e SNIPEIT_URL="https://assets.yourcompany.com" \
  -e SNIPEIT_API_TOKEN="token" \
  -e CHECKWARRANTY_API_KEY="cw_live_..." \
  ghcr.io/checkwarranty/snipeit-warranty-sync:latest --limit 100
```

Or add to Linux cron (`crontab -e`):
```bash
0 2 * * * cd /opt/snipeit-warranty-sync && python3 sync.py >> /var/log/snipeit-sync.log 2>&1
```

---

## Resources & Discussion

- **GitHub Repository:** [checkwarranty/snipeit-warranty-sync](https://github.com/checkwarranty/snipeit-warranty-sync)
- **Snipe-IT Community Discussion:** [github.com/grokability/snipe-it/discussions/19966](https://github.com/grokability/snipe-it/discussions/19966)
- **Reddit Thread:** [reddit.com/r/Snipe_IT](https://www.reddit.com/r/Snipe_IT/s/vmctFzA13T)
- **CheckWarranty API Documentation:** [checkwarranty.info/docs/api](https://checkwarranty.info/docs/api)

Most IT teams running Snipe-IT maintain thousands of serial numbers, but fields like warranty expiration dates and factory hardware specifications (CPU, RAM, SSD) often remain completely blank.

Checking warranty portals manually for Dell, Lenovo, HP, and Apple laptops isn’t scalable — it leads to unbudgeted repair costs and blind spots during hardware refresh cycles.

To automate this, we built and open-sourced `snipeit-warranty-sync`:
👉 GitHub: https://github.com/checkwarranty/snipeit-warranty-sync

Here is how it works under the hood:
1. Queries your Snipe-IT hardware API for assets missing warranty dates.
2. Identifies brand and queries CheckWarranty API for confirmed warranty coverage & factory BOM configurations.
3. Automatically computes `warranty_months` and `purchase_date` so Snipe-IT’s native calculated expiration fields update seamlessly.
4. Maps factory hardware specs (CPU model, RAM, SSD capacity) directly into Snipe-IT Custom Fields.

Key highlights:
* Zero external pip dependencies (built entirely on Python's standard library).
* Built-in `--dry-run` simulation mode to preview updates before touching live data.
* Docker-ready (`ghcr.io/checkwarranty/snipeit-warranty-sync:latest`) for daily unattended cron runs.

Full technical walkthrough on Dev.to:
https://dev.to/luksiko/automating-hardware-warranty-tracking-and-factory-specs-in-snipe-it-itam-dig

We also opened PR #19967 to the official Snipe-IT documentation repository. Hope this helps anyone managing enterprise IT hardware!

#ITAM #SysAdmin #SnipeIT #ITOperations #OpenSource #AssetManagement #DevOps

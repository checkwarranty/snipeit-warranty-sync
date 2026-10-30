import argparse
import json
import os
import pathlib
import sys
import threading
from http.server import HTTPServer
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
import checkwarranty_snipeit_sync as sync
from mock_api import Handler, REQUESTS
server = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
auth = json.loads(pathlib.Path("/tmp/cw-snipe-auth.json").read_text())
os.environ.update(SNIPEIT_URL="http://127.0.0.1:18080", SNIPEIT_API_TOKEN=auth["token"], CHECKWARRANTY_API_KEY="acceptance-sandbox-only", CHECKWARRANTY_API_URL="http://127.0.0.1:"+str(server.server_port)+"/api/v1", FIELD_WARRANTY_EXPIRATION=auth["field"])
args = argparse.Namespace(dry_run=False, plan=True, limit=100, force=True, brand=None, verbose=False)
sync.run_sync(args)
assert not REQUESTS
args.plan=False
with patch.object(sync.time, "sleep"):
    sync.run_sync(args)
client = sync.SnipeItClient(os.environ["SNIPEIT_URL"], auth["token"])
rows = {row["serial"]: row for row in client.get_hardware_assets()}
for kind in ("ENDONLY", "FULL", "ASYNC"):
    row = rows["TEST-"+kind]
    value = row["custom_fields"]["Warranty Expiration"]["value"]
    assert value == ("2027-01-01" if kind == "FULL" else "2027-01-05"), (kind, value)
assert sync.extract_snipe_date(rows["TEST-FULL"]["purchase_date"]) == "2020-03-01"
assert not sync.extract_snipe_date(rows["TEST-ENDONLY"]["purchase_date"])
assert not rows["TEST-NOTFOUND"]["custom_fields"]["Warranty Expiration"]["value"]
assert len(REQUESTS) == 4
server.shutdown()
print("Snipe-IT 8.8.3 REST acceptance passed (purchase preservation, exact expiry, plan, not-found, async)")

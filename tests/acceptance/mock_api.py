"""Deterministic public B2B DTO fixture server. Never forwards to a live API."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

REQUESTS = []


def fixture(serial):
    warranty = {"status": "active", "endDate": "2027-01-05", "coverageType": "ProSupport", "details": {"processor": "Xeon <script>alert(1)</script>"}}
    if "FULL" in serial:
        warranty.update(startDate="2024-01-01", endDate="2027-01-01")
    if "SPECS" in serial:
        warranty = {"status": "unknown", "details": {"processor": "Xeon"}}
    if "NOTFOUND" in serial:
        warranty = {"status": "not_found", "startDate": None, "endDate": None, "details": {"message": "missing"}}
    return {"status": "completed", "device": {"brand": "dell", "serialNumber": serial}, "warranty": warranty, "credits": {"used": 0, "remaining": 100}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, value, status=200):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        serial = data.get("serialNumber", "")
        REQUESTS.append({"serial": serial, "key": self.headers.get("Idempotency-Key")})
        if "ERROR" in serial:
            self.send({"status": "error"}, 503)
        elif "ASYNC" in serial:
            self.send({"status": "in_progress", "batchId": "00000000-0000-4000-8000-000000000001"}, 202)
        else:
            self.send(fixture(serial))

    def do_GET(self):
        if self.path == "/_stats":
            self.send(REQUESTS)
        elif "/devices/scans/" in self.path:
            self.send({"status": "completed", "items": [fixture("TEST-ASYNC")]})
        else:
            self.send({"status": "not_found"}, 404)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8000), Handler).serve_forever()

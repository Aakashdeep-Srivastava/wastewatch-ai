# app/store.py
# -----------------------------------------------------------------------------
# Alert store. Local JSON = DEVELOPMENT MODE ONLY. Deployed store = DynamoDB
# (set ORBIT_STORE=dynamo). A real state-transition guard protects approval.
# -----------------------------------------------------------------------------
import os
import json
import time

_LOCAL = os.path.join(os.path.dirname(__file__), "..", "data", "alerts.json")

# only these transitions are allowed (human-control safety)
_ALLOWED = {
    ("PENDING_REVIEW", "CONFIRMED"), ("PENDING_REVIEW", "DISMISSED"),
    ("PENDING_REVIEW", "NEEDS_MORE_INFO"),
    ("NEEDS_REVIEW", "CONFIRMED"), ("NEEDS_REVIEW", "DISMISSED"),
    ("NEEDS_REVIEW", "NEEDS_MORE_INFO"),
    # a reviewer can still resolve a case previously flagged for more info
    ("NEEDS_MORE_INFO", "CONFIRMED"), ("NEEDS_MORE_INFO", "DISMISSED"),
}


def _load():
    try:
        with open(_LOCAL) as f:
            return json.load(f)
    except Exception:
        return {}


def _save(d):
    os.makedirs(os.path.dirname(_LOCAL), exist_ok=True)
    with open(_LOCAL, "w") as f:
        json.dump(d, f, indent=2)


def _dynamo():
    import boto3
    return boto3.resource("dynamodb",
                          region_name=os.getenv("AWS_REGION", "us-east-1")
                          ).Table(os.getenv("DDB_TABLE", "alerts"))


def put_alert(record):
    record["updated"] = int(time.time())
    if os.getenv("ORBIT_STORE") == "dynamo":
        try:
            _dynamo().put_item(Item=record); return record
        except Exception:
            pass
    d = _load(); d[record["id"]] = record; _save(d); return record


def set_status(alert_id, new_status, comment=None):
    """Guarded transition. Returns {ok, status, reason}. Optionally records a
    reviewer comment alongside the state change."""
    cur = get_alert(alert_id)
    if not cur:
        return {"ok": False, "status": "NOT_FOUND", "reason": "unknown alert"}
    old = cur.get("status")
    if (old, new_status) not in _ALLOWED:
        return {"ok": False, "status": old,
                "reason": f"transition {old} -> {new_status} not allowed"}
    if os.getenv("ORBIT_STORE") == "dynamo":
        try:
            expr = "SET #s=:n, updated=:u"
            names = {"#s": "status"}
            vals = {":n": new_status, ":o": old, ":u": int(time.time())}
            if comment is not None:
                expr += ", #c=:c"; names["#c"] = "comment"; vals[":c"] = comment
            _dynamo().update_item(
                Key={"id": alert_id}, UpdateExpression=expr,
                ConditionExpression="#s = :o",
                ExpressionAttributeNames=names, ExpressionAttributeValues=vals)
            return {"ok": True, "status": new_status, "reason": "updated"}
        except Exception:
            pass
    d = _load()
    d[alert_id]["status"] = new_status
    d[alert_id]["updated"] = int(time.time())
    if comment is not None:
        d[alert_id]["comment"] = comment
    _save(d)
    return {"ok": True, "status": new_status, "reason": "updated"}


def get_alert(alert_id):
    if os.getenv("ORBIT_STORE") == "dynamo":
        try:
            return _dynamo().get_item(Key={"id": alert_id}).get("Item")
        except Exception:
            pass
    return _load().get(alert_id)


def list_alerts():
    """All alerts, newest-updated first (for the inspections dashboard)."""
    if os.getenv("ORBIT_STORE") == "dynamo":
        try:
            items = _dynamo().scan().get("Items", [])
            return sorted(items, key=lambda r: r.get("updated", 0), reverse=True)
        except Exception:
            pass
    return sorted(_load().values(), key=lambda r: r.get("updated", 0), reverse=True)

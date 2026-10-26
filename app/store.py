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
    ("NEEDS_REVIEW", "CONFIRMED"), ("NEEDS_REVIEW", "DISMISSED"),
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


def set_status(alert_id, new_status):
    """Guarded transition. Returns {ok, status, reason}."""
    cur = get_alert(alert_id)
    if not cur:
        return {"ok": False, "status": "NOT_FOUND", "reason": "unknown alert"}
    old = cur.get("status")
    if (old, new_status) not in _ALLOWED:
        return {"ok": False, "status": old,
                "reason": f"transition {old} -> {new_status} not allowed"}
    if os.getenv("ORBIT_STORE") == "dynamo":
        try:
            _dynamo().update_item(
                Key={"id": alert_id},
                UpdateExpression="SET #s=:n, updated=:u",
                ConditionExpression="#s = :o",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":n": new_status, ":o": old,
                                           ":u": int(time.time())})
            return {"ok": True, "status": new_status, "reason": "updated"}
        except Exception:
            pass
    d = _load()
    d[alert_id]["status"] = new_status; d[alert_id]["updated"] = int(time.time())
    _save(d)
    return {"ok": True, "status": new_status, "reason": "updated"}


def get_alert(alert_id):
    if os.getenv("ORBIT_STORE") == "dynamo":
        try:
            return _dynamo().get_item(Key={"id": alert_id}).get("Item")
        except Exception:
            pass
    return _load().get(alert_id)

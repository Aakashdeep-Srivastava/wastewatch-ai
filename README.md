# OrbitWatch

Agentic satellite change detection for the **OpenCV AI Competition 2026 (powered by AWS)**.
OpenCV 5 is the eyes (it measures); an agent is the manager (it decides the next
action from what it saw); a human approves every alert.

- **Award target:** Agentic Vision Award + Grand Prize. COOL not pursued.
- **Impact:** illegal mining / encroachment / unauthorized-construction monitoring.

## What runs where
- **Eyes — `app/vision.py`** (OpenCV 5 only): `cloud_gate`, `coregister`
  (ORB + `findHomography(USAC_MAGSAC)` + `warpPerspective`), `refine_ecc`
  (`findTransformECC`), `detect_change` (CLAHE + Lab `absdiff` + Otsu +
  `connectedComponentsWithStats`), `zoom_region` (active perception).
- **Manager — `app/agent.py`**: a perception→decision→action loop. Two brains:
  `rule` (default, zero AWS) and `bedrock` (AWS model chooses the next tool).
- **Web — `app/main.py`**: `POST /inspect`, `GET /trace/{id}`, `POST /approve/{id}`, demo page at `/`.

## Run locally (works with NO AWS)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip freeze > requirements.lock          # pin exact versions
python -m pytest -q                      # smoke tests (proves OpenCV 5 APIs)
uvicorn app.main:app --host 0.0.0.0 --port 8000
# open http://localhost:8000  -> upload a before/after pair
```

## Turn on the AWS agent (optional)
```bash
export ORBIT_AGENT=bedrock
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=amazon.nova-lite-v1:0   # one you have access to
export ORBIT_STORE=dynamo DDB_TABLE=alerts      # optional DynamoDB
```
If boto3 or model access is missing, it silently falls back to the rule agent.

## Evaluation (headline numbers)
```bash
pip install datasets pillow
python eval.py        # OSCD change-pixel F1 + saves failure examples
```

## Deploy on AWS (Graviton)
See `deploy/ec2_setup.sh`. One `t4g.small` + Elastic IP running uvicorn.

## Responsible use
No automatic enforcement. The system flags change for human review; a person
clicks Approve/Dismiss before anything is treated as confirmed. On any tool
failure the agent defaults to `NEEDS_HUMAN_REVIEW`, never a silent pass.

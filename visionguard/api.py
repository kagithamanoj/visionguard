"""FastAPI front end for VisionGuard.

POST /inspect  - multipart image upload, returns the full pipeline verdict
GET  /metrics  - per-tenant metering from the policy gateway
GET  /health   - liveness probe

Run: uvicorn visionguard.api:app --host 0.0.0.0 --port 8000
"""
import os
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from .agents.actor import ActorAgent
from .agents.detector import DetectorAgent
from .agents.reasoner import ReasonerAgent
from .gateway.policy import PolicyDenied, PolicyGateway

app = FastAPI(title="VisionGuard", version="0.1.0")

_gateway = PolicyGateway()
_detector = DetectorAgent()
_reasoner = ReasonerAgent()
_actor = ActorAgent(audit=_gateway.audit)

from .pipeline import run_pipeline  # noqa: E402


@app.get("/health")
def health():
    return {"status": "ok", "service": "visionguard"}


@app.get("/metrics")
def metrics():
    return _gateway.get_metrics()


@app.post("/inspect")
async def inspect(image: UploadFile = File(...),
                  tenant: str = "default"):
    suffix = os.path.splitext(image.filename or "upload.png")[1] or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await image.read())
        tmp_path = tmp.name
    try:
        result = run_pipeline(tmp_path, tenant=tenant,
                              detector=_detector, reasoner=_reasoner,
                              actor=_actor, gateway=_gateway)
    except PolicyDenied as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return JSONResponse(result)

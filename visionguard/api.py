"""FastAPI front end for VisionGuard.

POST /inspect  - multipart image upload, returns the full pipeline verdict
GET  /metrics  - per-tenant metering from the policy gateway
GET  /health   - liveness probe (no auth)

Tenants with a configured API key must send it as the X-API-Key header.
Keys are set through the VISIONGUARD_API_KEYS env var (JSON mapping
tenant -> key); tenants without a key keep working unauthenticated.
Generate a key with: python scripts/new_api_key.py --tenant <name>

Run: uvicorn visionguard.api:app --host 0.0.0.0 --port 8000
"""
import os
import tempfile

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from .agents.actor import ActorAgent
from .agents.bedrock_judge import BedrockJudge
from .agents.detector import DetectorAgent
from .agents.reasoner import ReasonerAgent
from .gateway.policy import PolicyDenied, PolicyGateway

app = FastAPI(title="VisionGuard", version="0.1.0")

_gateway = PolicyGateway.from_env()
_detector = DetectorAgent()
# Bedrock judge is off unless VISIONGUARD_LLM_JUDGE_ENABLED=true.
_reasoner_judge = BedrockJudge.from_env()
_reasoner = ReasonerAgent(
    judge=_reasoner_judge if _reasoner_judge.enabled else None)
_actor = ActorAgent(audit=_gateway.audit)

from .pipeline import run_pipeline  # noqa: E402


async def _require_api_key(
        tenant: str = "default",
        x_api_key: str = Header(default=None, alias="X-API-Key")) -> str:
    """Check the tenant's API key through the gateway before anything
    else runs. Missing or wrong keys get a 401 and never reach metering."""
    allowed, reason = _gateway.check_api_key(tenant, x_api_key)
    if not allowed:
        raise HTTPException(status_code=401, detail=reason,
                            headers={"WWW-Authenticate": "ApiKey"})
    return x_api_key or ""


@app.get("/health")
def health():
    return {"status": "ok", "service": "visionguard"}


@app.get("/metrics")
def metrics(tenant: str = "default", api_key: str = Depends(_require_api_key)):
    return {"tenant": tenant, "metrics": _gateway.get_metrics().get(tenant, {})}


@app.post("/inspect")
async def inspect(image: UploadFile = File(...),
                  tenant: str = "default",
                  api_key: str = Depends(_require_api_key)):
    suffix = os.path.splitext(image.filename or "upload.png")[1] or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await image.read())
        tmp_path = tmp.name
    try:
        result = run_pipeline(tmp_path, tenant=tenant,
                              detector=_detector, reasoner=_reasoner,
                              actor=_actor, gateway=_gateway,
                              api_key=api_key or None)
    except PolicyDenied as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
    return JSONResponse(result)

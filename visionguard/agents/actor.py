"""Action agent: carries out the verdict.

Actions are deliberately boring and reversible: quarantine is a file copy,
alerts are a log line plus an optional webhook POST, and every action is
reported back so the caller can audit it. The agent never deletes the
original image.
"""
import json
import os
import shutil
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import urllib.request


class ActorAgent:
    # severity -> actions taken for it
    DEFAULT_POLICY = {
        "none": [],
        "minor": ["log"],
        "major": ["log", "quarantine"],
        "critical": ["log", "quarantine", "alert"],
    }

    def __init__(self,
                 quarantine_dir: str = "quarantine",
                 webhook_url: Optional[str] = None,
                 action_policy: Optional[Dict[str, List[str]]] = None,
                 audit: Optional[Callable[[dict], None]] = None):
        self.quarantine_dir = quarantine_dir
        self.webhook_url = webhook_url
        self.action_policy = action_policy or dict(self.DEFAULT_POLICY)
        self.audit = audit or (lambda entry: None)

    def _quarantine(self, image_path: str) -> str:
        os.makedirs(self.quarantine_dir, exist_ok=True)
        dest = os.path.join(self.quarantine_dir,
                            os.path.basename(image_path))
        shutil.copy2(image_path, dest)
        return dest

    def _alert(self, image_path: str, verdict) -> bool:
        payload = {
            "event": "visionguard.alert",
            "image": os.path.basename(image_path),
            "severity": verdict.severity,
            "confidence": verdict.confidence,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        print(f"ALERT [{payload['severity']}] {payload['image']} "
              f"confidence={payload['confidence']}")
        if not self.webhook_url:
            return False
        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=10):
                pass
            return True
        except Exception as exc:  # webhook is best-effort
            print(f"webhook failed (non-fatal): {exc}")
            return False

    def act(self, image_path: str, verdict, tenant: str = "default") -> dict:
        actions = self.action_policy.get(verdict.severity, ["log"])
        taken: Dict[str object] = {"actions": [], "tenant": tenant}
        for action in actions:
            if action == "quarantine":
                dest = self._quarantine(image_path)
                taken["actions"].append("quarantine")
                taken["quarantine_path"] = dest
            elif action == "alert":
                sent = self._alert(image_path, verdict)
                taken["actions"].append("alert")
                taken["webhook_sent"] = sent
            elif action == "log":
                taken["actions"].append("log")
        taken["severity"] = verdict.severity
        self.audit({
            "type": "action",
            "tenant": tenant,
            "image": os.path.basename(image_path),
            "severity": verdict.severity,
            "actions": taken["actions"],
            "at": datetime.now(timezone.utc).isoformat(),
        })
        return taken

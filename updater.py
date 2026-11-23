import json
import urllib.error
import urllib.request

VERSION_URL = "https://raw.githubusercontent.com/cyperrrr/recoil-panel-updates/main/version.json"


def _ver_tuple(v: str) -> tuple[int, ...]:
    parts = []
    for part in str(v).strip().lstrip("vV").split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def check_update(current_version: str, timeout: float = 3.5) -> dict:
    try:
        req = urllib.request.Request(
            VERSION_URL,
            headers={
                "User-Agent": "RecoilPanelUpdater/1.0",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        latest = str(data.get("version", current_version))
        return {
            "ok": True,
            "has_update": _ver_tuple(latest) > _ver_tuple(current_version),
            "latest": latest,
            "notes": str(data.get("notes", "")),
            "url": str(data.get("url", "")),
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        return {"ok": False, "has_update": False, "error": str(e)}

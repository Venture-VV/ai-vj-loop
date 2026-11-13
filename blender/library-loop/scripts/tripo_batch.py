#!/usr/bin/env python3
"""
Generate every model in tripo/assets.json with the Tripo OpenAPI (v3) and save the GLBs where
import_tripo.py expects them: assets/models/<id>.glb

    export TRIPO_API_KEY=tsk_...              (Windows PowerShell:  $env:TRIPO_API_KEY="tsk_...")
    python scripts/tripo_batch.py --dry-run          # show what would be sent, spend nothing
    python scripts/tripo_batch.py                    # all required assets, one variant each
    python scripts/tripo_batch.py --only hero_3_michael_dragon --variants 3
    python scripts/tripo_batch.py --optional         # also the optional props
    python scripts/tripo_batch.py --moderated hero_1_demon_rising   # use the softer prompt

Image-to-3D instead of text-to-3D: drop a concept image at tripo/images/<id>.png (or .jpg/.webp)
and that asset is generated from the image (more control over the pose; 20 credits instead of 10).

Requests prefer system curl (HTTP/2) when available, with a Python standard-library fallback.
Credentials are passed to curl through stdin, never its arguments or environment.
Task ids are stored in tripo/tasks.json, so a run that is
interrupted (or times out) is resumed instead of paid for twice.

NOTE  written against https://developers.tripo3d.ai (API v3), then exercised locally against the
      CN API on 2026-11-12. If a response has an unexpected shape the script prints it and stops.
      API credits are billed separately from a Tripo Studio (web) subscription.
"""
import argparse, http.client, json, mimetypes, os, re, shutil, struct, subprocess, sys, time, urllib.error, urllib.request, uuid
from datetime import datetime, timezone
from urllib.parse import urlencode

BASE = os.environ.get("TRIPO_API_BASE", "https://openapi.tripo3d.ai/v3")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MANIFEST = os.path.join(ROOT, "tripo", "assets.json")
STATE = os.path.join(ROOT, "tripo", "tasks.json")
IMAGES = os.path.join(ROOT, "tripo", "images")
MODELS = os.path.join(ROOT, "assets", "models")
TERMINAL_BAD = ("failed", "cancelled", "banned", "expired")
DOWNLOAD_CHUNK = 1 << 20


def key():
    k = os.environ.get("TRIPO_API_KEY", "").strip()
    if not k:
        sys.exit("TRIPO_API_KEY is not set (create one at https://developers.tripo3d.ai, it starts with tsk_)")
    return k


def call(method, path, body=None, raw=None, content_type=None):
    # Read-only polling may retry transient transport errors. Creation is never retried.
    for attempt in range(4):
        try:
            if raw is None and shutil.which("curl"):
                return call_curl(method, path, body)
            return call_once(method, path, body, raw, content_type)
        except (urllib.error.URLError, http.client.RemoteDisconnected, http.client.IncompleteRead, TimeoutError, ConnectionError) as exc:
            if method != "GET" or attempt == 3:
                raise
            print("Read-only query interrupted: %s: %s; retrying the same task in %ss" %
                  (type(exc).__name__, str(exc).replace(key(), "[REDACTED]"), 2 ** (attempt + 1)), flush=True)
            time.sleep(2 ** (attempt + 1))


def call_curl(method, path, body=None):
    """Keep the Bearer credential in stdin, never argv, files or a child's environment."""
    command = [shutil.which("curl"), "--silent", "--show-error", "--fail-with-body", "--http2",
               "--connect-timeout", "15", "--max-time", "90", "--request", method, "--config", "-",
               "--url", BASE + path, "--write-out", "\n__TRIPO_HTTP__%{http_code}"]
    proxy = urllib.request.getproxies().get("https")
    if proxy:
        command += ["--proxy", proxy]
    config = 'header = ' + json.dumps("Authorization: Bearer " + key()) + '\n'
    if body is not None:
        config += 'header = "Content-Type: application/json"\n'
        config += 'data = ' + json.dumps(json.dumps(body)) + '\n'
    environment = os.environ.copy()
    environment.pop("TRIPO_API_KEY", None)
    result = subprocess.run(command, input=config, capture_output=True, text=True, env=environment)
    body_text, marker, status = result.stdout.rpartition("\n__TRIPO_HTTP__")
    if result.returncode or not marker or status != "200":
        detail = (body_text + '\n' + result.stderr).replace(key(), "[REDACTED]")
        message = "HTTP %s on %s %s (curl %s)\n%s" % (status or "unknown", method, path, result.returncode, detail)
        if status in ("000", "429", "500", "502", "503", "504"):
            raise urllib.error.URLError(message)
        raise SystemExit(message)
    payload = json.loads(body_text)
    if not isinstance(payload, dict) or payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
        raise SystemExit("Unexpected response on %s %s:\n%s" % (method, path, body_text.replace(key(), "[REDACTED]")))
    return payload["data"]


def call_once(method, path, body=None, raw=None, content_type=None):
    url = BASE + path
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + key())
    if data is not None:
        req.add_header("Content-Type", content_type or "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            payload = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        text = e.read().decode(errors="replace").replace(key(), "[REDACTED]")
        raise SystemExit("HTTP %s on %s %s\n%s" % (e.code, method, path, text))
    if not isinstance(payload, dict) or payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
        raise SystemExit("unexpected response on %s %s:\n%s" %
                         (method, path, json.dumps(payload, indent=2).replace(key(), "[REDACTED]")))
    return payload["data"]


def save_state(state):
    """Atomic journal: an ambiguous submission must never be silently submitted again."""
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE)


def estimate_credits(path, payload):
    if payload["model"] != "v3.1-20260211":
        raise SystemExit("No verified price for model: " + payload["model"])
    cost = 20 if path == "/generation/image-to-model" else 10
    return cost + (10 if payload["texture"] or payload["pbr"] else 0) + (20 if payload.get("geometry_quality") == "detailed" else 0)


def upload(path):
    boundary = uuid.uuid4().hex
    ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        blob = f.read()
    body = (("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
             % (boundary, os.path.basename(path), ctype)).encode() + blob + ("\r\n--%s--\r\n" % boundary).encode())
    data = call("POST", "/files", raw=body, content_type="multipart/form-data; boundary=" + boundary)
    token = data.get("file_token")
    if not token:
        raise SystemExit("upload: no file_token in " + json.dumps(data))
    return token


def find_image(asset_id):
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = os.path.join(IMAGES, asset_id + ext)
        if os.path.exists(p):
            return p
    return None


def payload_for(asset, defaults, suffix, textured, moderated):
    p = {
        "model": asset.get("model", defaults["model"]),
        "texture": bool(textured),
        "pbr": bool(textured),                 # pbr defaults to true server-side and forces texture on
        "face_limit": asset.get("face_limit", 200000),
    }
    gq = asset.get("geometry_quality", defaults.get("geometry_quality"))
    if gq and gq != "standard":
        p["geometry_quality"] = gq
    img = find_image(asset["id"])
    if img:
        return "/generation/image-to-model", p, img
    text = asset.get("prompt_if_moderated") if (moderated and asset.get("prompt_if_moderated")) else asset["prompt"]
    p["prompt"] = (text + (suffix if asset.get("slot") else ""))[:1024]     # the sculpture style suffix is for the heroes only
    p["negative_prompt"] = defaults.get("negative_prompt", "")[:255]
    return "/generation/text-to-model", p, None


def download(url, dest):
    curl = shutil.which("curl")
    if curl:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".part"
        command = [curl, "--silent", "--show-error", "--location", "--fail", "--http2", "--connect-timeout", "15",
                   "--max-time", "180", "--retry", "3", "--retry-delay", "2", "--retry-all-errors",
                   "--header", "Accept-Encoding: identity", "--output", tmp,
                   "--write-out", "http=%{http_code} bytes=%{size_download} time=%{time_total}"]
        if os.path.isfile(tmp):
            with open(tmp, "rb") as f:
                header = f.read(12)
            if len(header) == 12 and header[:8] == b"glTF\x02\x00\x00\x00":
                declared = struct.unpack("<I", header[8:])[0]
                existing = os.path.getsize(tmp)
                if existing == declared:
                    validate_glb(tmp, dest)
                    os.replace(tmp, dest)
                    return
                if 12 <= existing < declared:
                    command += ["--continue-at", "-"]
                    print("resume download", os.path.basename(dest), "%s/%s bytes" % (existing, declared), flush=True)
        proxy = urllib.request.getproxies().get("https")
        if proxy:
            command += ["--proxy", proxy]
        environment = os.environ.copy()
        environment.pop("TRIPO_API_KEY", None)
        result = subprocess.run(command + ["--url", url], capture_output=True, text=True, env=environment)
        if result.returncode:
            raise SystemExit("Model download failed (curl %s):\n%s" % (result.returncode, result.stderr))
        validate_glb(tmp, dest)
        os.replace(tmp, dest)
        print("download", os.path.basename(dest), result.stdout, flush=True)
        return
    for attempt in range(4):
        try:
            return download_once(url, dest)
        except (urllib.error.URLError, http.client.RemoteDisconnected, http.client.IncompleteRead, TimeoutError, ConnectionError, SystemExit) as exc:
            if isinstance(exc, SystemExit) and not str(exc).startswith("Invalid or incomplete GLB download:"):
                raise
            if attempt == 3:
                raise
            print("Model download interrupted: %s: %s; retrying the existing result in %ss" %
                  (type(exc).__name__, str(exc), 2 ** (attempt + 1)), flush=True)
            time.sleep(2 ** (attempt + 1))


def download_once(url, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    offset, total = 0, None
    with open(tmp, "wb") as f:
        while total is None or offset < total:
            end = offset + DOWNLOAD_CHUNK - 1 if total is None else min(total - 1, offset + DOWNLOAD_CHUNK - 1)
            # Signed model URL only: never forward the API Authorization header.
            req = urllib.request.Request(url, headers={"Range": "bytes=%d-%d" % (offset, end), "Accept-Encoding": "identity"})
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(req, timeout=90) as r:
                        status = getattr(r, "status", 200)
                        headers = getattr(r, "headers", {})
                        content_range = headers.get("Content-Range", "")
                        if status == 206:
                            match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", content_range)
                            if not match:
                                raise ValueError("Invalid Content-Range: " + content_range)
                            start, last, length = map(int, match.groups())
                            if start != offset or last != min(end, length - 1) or (total is not None and total != length):
                                raise ValueError("Unexpected Content-Range: " + content_range)
                            chunk = r.read(last - start + 2)
                            if len(chunk) != last - start + 1:
                                raise ValueError("Truncated byte range %s: received %s" % (content_range, len(chunk)))
                            total = length
                        elif status == 200 and offset == 0:
                            # A server may ignore Range; validate the complete GLB below.
                            chunk = r.read()
                            total = len(chunk)
                        else:
                            raise ValueError("Unexpected download HTTP status %s at offset %s" % (status, offset))
                    break
                except (urllib.error.URLError, http.client.RemoteDisconnected, http.client.IncompleteRead, TimeoutError, ConnectionError, ValueError) as exc:
                    if attempt == 3:
                        raise
                    print("Download range %s interrupted: %s: %s; retrying the same bytes" %
                          (offset, type(exc).__name__, str(exc)), flush=True)
                    time.sleep(2 ** (attempt + 1))
            f.write(chunk)
            offset += len(chunk)
            if not chunk:
                break
    validate_glb(tmp, dest)
    os.replace(tmp, dest)


def validate_glb(tmp, dest):
    with open(tmp, "rb") as f:
        header = f.read(12)
    if len(header) != 12 or header[:4] != b"glTF" or struct.unpack("<II", header[4:]) != (2, os.path.getsize(tmp)):
        declared = struct.unpack("<I", header[8:12])[0] if len(header) == 12 and header[:4] == b"glTF" else None
        raise SystemExit("Invalid or incomplete GLB download: %s (received=%s, declared=%s)" %
                         (os.path.basename(dest), os.path.getsize(tmp), declared))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma separated asset ids")
    ap.add_argument("--variants", type=int, default=1, help="how many seeds per asset (pick the best one, rename it to <id>.glb)")
    ap.add_argument("--optional", action="store_true", help="include assets marked optional")
    ap.add_argument("--textured", action="store_true", help="ask Tripo for PBR textures too (statues are re-shaded in Blender, so normally not needed)")
    ap.add_argument("--moderated", default="", help="comma separated ids that should use prompt_if_moderated")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--max-credits", type=float, default=400, help="maximum estimated credits for the entire selected plan")
    a = ap.parse_args()
    if a.variants < 1 or a.max_credits <= 0:
        ap.error("--variants and --max-credits must be positive")

    with open(MANIFEST, encoding="utf-8") as f:
        man = json.load(f)
    defaults, suffix = man["defaults"], man.get("style_suffix", "")
    only = {s for s in a.only.split(",") if s}
    moderated = {s for s in a.moderated.split(",") if s}
    assets = [x for x in man["assets"] if (x["id"] in only if only else (a.optional or not x.get("optional")))]
    if only - {x["id"] for x in assets}:
        ap.error("unknown asset id(s): " + ", ".join(sorted(only - {x["id"] for x in assets})))
    state = {}
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as f:
            state = json.load(f)

    jobs, planned = [], 0
    for asset in assets:
        for v in range(1, a.variants + 1):
            name = asset["id"] if v == 1 else "%s__v%d" % (asset["id"], v)
            dest = os.path.join(MODELS, name + ".glb")
            path, payload, img = payload_for(asset, defaults, suffix, a.textured, asset["id"] in moderated)
            expected = estimate_credits(path, payload)
            planned += expected
            if os.path.exists(dest):
                print("have   ", name)
                continue
            if v > 1:
                payload["model_seed"] = 1000 + v
            jobs.append(dict(name=name, dest=dest, path=path, payload=payload, img=img, expected=expected))

    print("planned credits: %s; approved limit: %s" % (planned, a.max_credits))
    if planned > a.max_credits:
        raise SystemExit("Estimated credits exceed the approved limit; no tasks submitted")

    if a.dry_run:
        for j in jobs:
            print("\n== %s  ->  POST %s%s" % (j["name"], BASE, j["path"]))
            if j["img"]:
                print("   image:", j["img"])
            print(json.dumps(j["payload"], indent=2, ensure_ascii=False))
        print("\n%d task(s) would be created." % len(jobs))
        return

    spent = 0.0
    for j in jobs:                                              # complete each job before submitting the next
        if j["name"] in state:
            j["task"] = state[j["name"]]
            if not isinstance(j["task"], str) or not j["task"]:
                if isinstance(j["task"], dict) and j["task"].get("submission_pending"):
                    start = datetime.fromtimestamp(j["task"]["created_at"] - 30, timezone.utc).isoformat()
                    end = datetime.now(timezone.utc).isoformat()
                    history = call("GET", "/account/usage/history?" + urlencode({"start_time": start, "end_time": end, "page_size": 100}))
                    audit = {"asset": j["name"], "submission": j["task"], "balance": call("GET", "/account/balance"), "history": history}
                    print("Pending submission read-only audit:\n" + json.dumps(audit, indent=2), flush=True)
                raise SystemExit("Uncertain earlier submission for %s; reconcile it with Tripo before retrying.\n%s" %
                                 (j["name"], json.dumps(j["task"], indent=2)))
            print("resume ", j["name"], j["task"])
        else:
            if j["img"]:
                j["payload"]["input"] = upload(j["img"])
            state[j["name"]] = {"submission_pending": True, "created_at": time.time(), "estimated_credits": j["expected"]}
            save_state(state)
            data = call("POST", j["path"], j["payload"])
            j["task"] = data.get("task_id")
            if not isinstance(j["task"], str) or not j["task"]:
                raise SystemExit("no task_id in " + json.dumps(data))
            state[j["name"]] = j["task"]
            save_state(state)
            print("submit ", j["name"], j["task"], flush=True)

        deadline = time.monotonic() + a.timeout
        previous = None
        while time.monotonic() < deadline:
            time.sleep(4)
            t = call("GET", "/tasks/" + j["task"])
            st = t.get("status")
            if st == "success":
                url = (t.get("output") or {}).get("model_url")
                if not url:
                    raise SystemExit("success without output.model_url:\n" + json.dumps(t, indent=2))
                os.makedirs(os.path.dirname(j["dest"]), exist_ok=True)
                with open(j["dest"] + ".json", "w", encoding="utf-8") as f:
                    json.dump({"task_id": j["task"], "credits_consumed": t.get("credits_consumed"),
                               "model_url": url, "created_at": t.get("created_at"), "completed_at": t.get("completed_at")}, f, indent=2)
                charged = t.get("credits_consumed")
                if not isinstance(charged, (int, float)) or not 0 <= charged <= j["expected"]:
                    raise SystemExit("Unexpected credits; remaining submissions stopped:\n" + json.dumps(t, indent=2))
                download(url, j["dest"])
                spent += charged
                print("done   ", j["name"], "->", os.path.relpath(j["dest"], ROOT), "(%s credits)" % t.get("credits_consumed"))
                break
            elif st in TERMINAL_BAD:
                raise SystemExit("FAILED %s; task id retained, no further submissions:\n%s" % (j["name"], json.dumps(t, indent=2)))
            elif st not in ("queued", "running"):
                raise SystemExit("Unexpected task status; task id retained:\n" + json.dumps(t, indent=2))
            else:
                progress = (st, t.get("progress"))
                if progress != previous:
                    print("  ...  %-28s %-8s %s%%" % (j["name"], *progress), flush=True)
                    previous = progress
        else:
            raise SystemExit("Task polling timed out; task id retained, no further submissions: " + j["task"])
    print("\ncredits consumed this run: %.0f" % spent)


if __name__ == "__main__":
    main()

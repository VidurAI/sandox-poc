#!/usr/bin/env python3
"""
CI gate for citizen-developer sandbox apps.

Reads app.yaml + the app directory, checks it against allowlist.yaml and the
manifest schema, and prints plain-language errors a citizen developer can act
on. Exit 0 = may proceed to build. Exit 1 = blocked.

This is the ENFORCEMENT layer. The Cowork skill is guidance only.
Both read the same allowlist.yaml; that is deliberate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "manifest" / "app.schema.json"
ALLOWLIST = ROOT / "allowlist.yaml"

# Things that must never be committed. Pattern -> what to tell the citizen dev.
SECRET_PATTERNS = {
    r"AKIA[0-9A-Z]{16}": "an AWS access key",
    r"sk-[A-Za-z0-9]{20,}": "an API key",
    r"(?i)(password|passwd|secret|token)\s*[=:]\s*['\"][^'\"]{8,}['\"]": "a hard-coded password or token",
    r"-----BEGIN (RSA |EC )?PRIVATE KEY-----": "a private key",
    r"(?i)postgres(ql)?://[^:]+:[^@]+@": "a database connection string with a password",
}

STACK_FILES = {
    "static": ["site/index.html"],
    "python-web": ["requirements.txt"],
}


def load_yaml(path: Path):
    with path.open() as f:
        return yaml.safe_load(f)


def check_manifest(manifest: dict, schema: dict) -> list[str]:
    errors = []
    for e in sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda e: list(e.path)):
        where = ".".join(str(p) for p in e.path) or "app.yaml"
        errors.append(f"{where}: {e.message}")
    return errors


def check_stack_files(app_dir: Path, stack: str) -> list[str]:
    missing = [f for f in STACK_FILES.get(stack, []) if not (app_dir / f).exists()]
    return [f"stack '{stack}' needs '{f}' but it is not in the repo" for f in missing]


def parse_requirements(path: Path) -> list[str]:
    names = []
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        # fastapi==0.1, uvicorn[standard]>=0.3, psycopg[binary]  -> base name
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", line)
        if m:
            names.append(m.group(1).lower().replace("_", "-"))
    return names


def check_dependencies(app_dir: Path, stack: str, allow: dict) -> list[str]:
    errors = []
    if stack == "python-web":
        req = app_dir / "requirements.txt"
        if req.exists():
            allowed = {n.lower() for n in allow.get("python", [])}
            for name in parse_requirements(req):
                if name not in allowed:
                    errors.append(
                        f"requirements.txt: '{name}' is not an approved package. "
                        f"Ask the platform team to add it, or use one of: {', '.join(sorted(allowed))}"
                    )
    if stack == "static":
        pkg = app_dir / "package.json"
        if pkg.exists():
            deps = json.loads(pkg.read_text()).get("dependencies", {})
            allowed = {n.lower() for n in allow.get("npm", [])}
            for name in deps:
                if name.lower() not in allowed:
                    errors.append(f"package.json: '{name}' is not approved. Static sites must be prebuilt with no runtime deps.")
    return errors


def check_egress(manifest: dict, allow: dict) -> list[str]:
    wanted = (manifest.get("needs") or {}).get("egress") or []
    allowed = set(allow.get("egress", []))
    return [
        f"needs.egress: '{fqdn}' is not on the platform egress allowlist. "
        f"The sandbox can only reach: {', '.join(sorted(allowed)) or 'nothing'}"
        for fqdn in wanted if fqdn not in allowed
    ]


def check_classification(manifest: dict, allow: dict) -> list[str]:
    dc = manifest.get("dataClassification")
    if dc and dc not in allow.get("dataClassification", []):
        return [f"dataClassification '{dc}' is not allowed in the sandbox. Use synthetic data and mark it 'synthetic-only'."]
    return []


def check_secrets(app_dir: Path) -> list[str]:
    errors = []
    skip = {".git", "node_modules", "__pycache__", ".venv"}
    for path in app_dir.rglob("*"):
        if not path.is_file() or any(part in skip for part in path.parts):
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for pattern, what in SECRET_PATTERNS.items():
            if re.search(pattern, text):
                errors.append(f"{path.relative_to(app_dir)}: looks like it contains {what}. Remove it; the sandbox provides credentials at deploy time.")
                break
    return errors


def check_forbidden_files(app_dir: Path) -> list[str]:
    """Citizen devs never touch infra. If Cowork emitted any, reject: it means the skill drifted."""
    forbidden = ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", "helm", "charts", "*.tf", "*.tfvars", ".github/workflows"]
    hits = []
    for pat in forbidden:
        hits += [str(p.relative_to(app_dir)) for p in app_dir.glob(pat)]
    return [f"'{h}' is infrastructure and is not allowed in a sandbox app. The platform provides it." for h in hits]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("app_dir", type=Path)
    ap.add_argument("--allowlist", type=Path, default=ALLOWLIST)
    ap.add_argument("--schema", type=Path, default=SCHEMA)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    app_dir: Path = args.app_dir.resolve()
    manifest_path = app_dir / "app.yaml"
    if not manifest_path.exists():
        print("BLOCKED: app.yaml is missing. Re-run the Cowork 'sandbox app' skill; it writes this file for you.")
        return 1

    manifest = load_yaml(manifest_path) or {}
    schema = json.loads(args.schema.read_text())
    allow = load_yaml(args.allowlist)

    errors = check_manifest(manifest, schema)
    stack = manifest.get("stack", "")
    # Run every check even if the schema failed, so the citizen dev sees the
    # whole list once instead of fixing one thing per push.
    if stack in STACK_FILES:
        errors += check_stack_files(app_dir, stack)
        errors += check_dependencies(app_dir, stack, allow)
        errors += check_egress(manifest, allow)
        errors += check_classification(manifest, allow)
    errors += check_secrets(app_dir)
    errors += check_forbidden_files(app_dir)

    if args.json:
        print(json.dumps({"ok": not errors, "app": manifest.get("name"), "stack": stack, "errors": errors}, indent=2))
    elif errors:
        print(f"BLOCKED: {manifest.get('name', app_dir.name)} cannot be deployed yet.\n")
        for e in errors:
            print(f"  - {e}")
        print("\nFix these and push again. Nothing was deployed.")
    else:
        print(f"OK: {manifest['name']} ({stack}) passed the sandbox gate.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

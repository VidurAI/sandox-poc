# Citizen-Dev App Sandbox — POC

Reference implementation for hosting Claude Cowork–generated apps in an
isolated non-prod Kubernetes namespace for business review, with a path to
Level 2 promotion. Companion to the Friday one-pager.

## What's here

| Path | What it is | Status |
| --- | --- | --- |
| `manifest/app.schema.json` | The one file a citizen dev's Cowork skill must emit | validated |
| `allowlist.yaml` | Single source of truth read by BOTH the skill and the gate | validated |
| `tools/gate.py` | CI enforcement: schema, deps, egress, secrets, forbidden infra files | **tested** — passes both examples, catches 6/6 planted violations |
| `tools/render_values.py` | `app.yaml` → `values.yaml`; the only "agent" step, and it's deterministic | **tested** |
| `charts/sandbox-app/` | One parametric Helm chart: namespace, quota, 2-layer default-deny, Istio, app, optional ephemeral Postgres | `helm lint` clean; renders 13 docs (static) / 19 docs (python-web + db) |
| `tests/negative_tests.sh` | Proves the sandbox denies internet, cross-namespace, IMDS, API server, and un-gatewayed ingress | bash-validated; **not yet run on a cluster** |
| `platform/ttl-reaper.yaml` | Hourly CronJob that deletes expired namespaces (ships in DRY_RUN) | YAML-validated |
| `build/Dockerfile.*` | Platform-owned per-stack Dockerfiles; app repos never have one | not built |
| `.github/workflows/sandbox.yml` | Template-repo workflow: gate → build+SCA → deploy+negative tests | YAML-validated; **not yet run** |
| `cowork-skill/SKILL.md` | The Cowork skill that constrains what citizen devs generate | drafted |
| `examples/` | One static site, one FastAPI app with a DB — the two pilot shapes | gate-passing |

## Try it locally (no cluster needed)

```bash
pip install pyyaml jsonschema
python3 tools/gate.py examples/python-web          # OK
python3 tools/gate.py examples/static-site         # OK
python3 tools/render_values.py examples/python-web --tag abc123 -o /tmp/v.yaml
helm template renewal-tracker charts/sandbox-app -f /tmp/v.yaml | less
```

## Honest status

- **Built and validated (~80% of the code):** gate logic, renderer, chart
  templates, workflow shape. Everything parses, lints, and renders.
- **Not done (~40% confidence until these run for real):**
  - Never deployed to a live AKS cluster. Istio `requestPrincipals` needs a
    `RequestAuthentication` on your gateway with the Entra issuer — not in
    this repo because it's gateway-side and I don't know your issuer.
  - `negative_tests.sh` has never executed. The SSO test is a shape, not a
    proof, until it runs against your real gateway.
  - Platform base images (`platform/python-web`, `nginx-unprivileged`) are
    referenced as `<your-acr>` placeholders; nothing is built.
  - FQDN → CIDR resolution for approved egress is a pipeline step that does
    not exist yet. On Cilium, replace with `CiliumNetworkPolicy` + `toFQDNs`.
- **Single biggest gap:** the negative-test suite running green on the real
  non-prod cluster. That is the integration test that turns this from a
  design into a proof. Budget days 6–7 of the pilot for exactly that.

## Design decisions baked in

1. Constrain the input via the Cowork skill; don't try to detect arbitrary stacks.
2. Deterministic build per stack; the agent only fills values.
3. One platform-owned chart; agent output is a reviewable `values.yaml` diff.
4. Default-deny at two layers: upstream `NetworkPolicy` (works on Azure NPM / Calico / Cilium) plus Istio `AuthorizationPolicy`. Istio alone is not sufficient.
5. Namespace-per-app with TTL; vCluster is a phase-2 swap, not a pilot dependency.
6. Ephemeral DB only, `emptyDir`, synthetic data only, gate rejects `confidential`.

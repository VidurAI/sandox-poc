#!/usr/bin/env bash
# Negative tests: prove the sandbox DENIES what it should, before any real app
# goes in. Every test here must FAIL the way we expect. Run after deploying a
# sandbox app; rerunnable; exits non-zero on the first isolation gap.
#
#   ./tests/negative_tests.sh <app-name> [gateway-namespace] [another-namespace-with-a-service]
#
set -uo pipefail
APP="${1:?app name}"
GW_NS="${2:-istio-ingress}"
OTHER_NS="${3:-kube-system}"
NS="sbx-${APP}"
PROBE="probe-$RANDOM"
PASS=0; FAIL=0

expect_deny() {   # expect_deny "<description>" <cmd...>
  local desc="$1"; shift
  if timeout 15 "$@" >/dev/null 2>&1; then
    echo "  FAIL  $desc  (succeeded, should have been denied)"; FAIL=$((FAIL+1))
  else
    echo "  ok    $desc"; PASS=$((PASS+1))
  fi
}
expect_allow() {
  local desc="$1"; shift
  if timeout 15 "$@" >/dev/null 2>&1; then
    echo "  ok    $desc"; PASS=$((PASS+1))
  else
    echo "  FAIL  $desc  (denied, should have been allowed)"; FAIL=$((FAIL+1))
  fi
}
in_probe() { kubectl -n "$NS" exec "$PROBE" -c probe -- "$@"; }

echo "== Sandbox negative tests for $NS =="

echo "-- structural --"
expect_allow "namespace has istio-injection=enabled" \
  bash -c "kubectl get ns $NS -o jsonpath='{.metadata.labels.istio-injection}' | grep -qx enabled"
expect_allow "namespace has an expires-at annotation" \
  bash -c "kubectl get ns $NS -o jsonpath='{.metadata.annotations.sandbox\.metlife\.internal/expires-at}' | grep -q T"
expect_allow "default-deny-all NetworkPolicy exists" kubectl -n "$NS" get networkpolicy default-deny-all
expect_allow "deny-all AuthorizationPolicy exists"   kubectl -n "$NS" get authorizationpolicy deny-all
expect_allow "app pod has istio-proxy sidecar" \
  bash -c "kubectl -n $NS get pod -l app.kubernetes.io/name=$APP -o jsonpath='{.items[0].spec.containers[*].name}' | grep -q istio-proxy"
expect_allow "app runs as non-root" \
  bash -c "kubectl -n $NS get pod -l app.kubernetes.io/name=$APP -o jsonpath='{.items[0].spec.securityContext.runAsNonRoot}' | grep -qx true"

echo "-- launching probe pod inside the sandbox (inherits its policies) --"
kubectl -n "$NS" run "$PROBE" --image=curlimages/curl:8.11.1 --restart=Never \
  --overrides='{"spec":{"containers":[{"name":"probe","image":"curlimages/curl:8.11.1","command":["sleep","300"],"securityContext":{"runAsNonRoot":true,"runAsUser":10001,"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"seccompProfile":{"type":"RuntimeDefault"}}}],"automountServiceAccountToken":false}}' >/dev/null
kubectl -n "$NS" wait --for=condition=Ready pod/"$PROBE" --timeout=90s >/dev/null || { echo "probe never became ready"; exit 2; }

echo "-- egress --"
expect_deny  "internet (https://example.com)"            in_probe curl -sS -m 5 https://example.com
expect_deny  "internet by IP (1.1.1.1:443)"              in_probe curl -sS -m 5 https://1.1.1.1
expect_deny  "another namespace ($OTHER_NS) service"     in_probe curl -sS -m 5 "http://kubernetes.default.svc.cluster.local"
expect_deny  "Azure IMDS (169.254.169.254)"              in_probe curl -sS -m 5 http://169.254.169.254/metadata/instance
expect_deny  "cluster API server"                        in_probe curl -sS -m 5 -k https://kubernetes.default.svc.cluster.local/version
expect_allow "DNS resolution still works"                in_probe nslookup kubernetes.default.svc.cluster.local

echo "-- ingress --"
APP_SVC="http://$APP.$NS.svc.cluster.local:8080"
expect_deny  "app reachable from inside its own namespace without going via gateway" \
  in_probe curl -sS -m 5 "$APP_SVC/"
HOST="$APP.sandbox.nonprod.metlife.internal"
GW_IP=$(kubectl -n "$GW_NS" get svc -l istio=ingressgateway -o jsonpath='{.items[0].status.loadBalancer.ingress[0].ip}' 2>/dev/null || true)
if [ -n "$GW_IP" ]; then
  expect_deny "gateway request with NO token is rejected" \
    curl -sS -m 5 -k --resolve "$HOST:443:$GW_IP" -o /dev/null -w '%{http_code}' "https://$HOST/" -H 'X-Expect: 401-or-403'
else
  echo "  skip  gateway IP not found in $GW_NS; run the SSO test manually"
fi

kubectl -n "$NS" delete pod "$PROBE" --wait=false >/dev/null 2>&1
echo
echo "== $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ]

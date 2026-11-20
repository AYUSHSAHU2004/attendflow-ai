#!/bin/sh
# Create or update the AttendFlow Kubernetes secrets from your shell environment.
# Values are written to a private temporary folder, passed to kubectl as files (never as
# command-line arguments) and never printed.
#
# Required:  POSTGRES_PASSWORD, ATTENDFLOW_SESSION_SECRET, ATTENDFLOW_DEMO_PASSWORD
# Optional:  LLM_API_KEY                 (the Groq key; without it the app uses templates)
#            GHCR_USERNAME + GHCR_TOKEN  (also creates the ghcr-pull image pull secret)
#            ATTENDFLOW_NAMESPACE        (default: attendflow)
#
# Example:
#   export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
#   export ATTENDFLOW_SESSION_SECRET="$(openssl rand -hex 32)"
#   export ATTENDFLOW_DEMO_PASSWORD="$(openssl rand -hex 24)"
#   read -rs LLM_API_KEY && export LLM_API_KEY
#   sh scripts/k8s-create-secrets.sh
#
# POSTGRES_PASSWORD is used by Postgres only when its volume is first created. To change it
# later, change it inside Postgres too (ALTER USER), or the app can no longer connect.
set -eu

NAMESPACE="${ATTENDFLOW_NAMESPACE:-attendflow}"

fail() {
    echo "k8s-create-secrets: $1" >&2
    exit 1
}

command -v kubectl >/dev/null 2>&1 || fail "kubectl is not on PATH"

for name in POSTGRES_PASSWORD ATTENDFLOW_SESSION_SECRET ATTENDFLOW_DEMO_PASSWORD; do
    eval "value=\${$name:-}"
    [ -n "$value" ] || fail "set $name first (see the comment at the top of this script)"
done
unset value

# The app refuses to start with a short session secret or a weak demo password.
[ "$(printf '%s' "$ATTENDFLOW_SESSION_SECRET" | wc -c)" -ge 32 ] \
    || fail "ATTENDFLOW_SESSION_SECRET must be at least 32 bytes (openssl rand -hex 32)"
[ "$(printf '%s' "$ATTENDFLOW_DEMO_PASSWORD" | wc -c)" -ge 32 ] \
    || fail "ATTENDFLOW_DEMO_PASSWORD must be at least 32 characters (openssl rand -hex 24)"

# The password goes into a URL, so percent-encode anything outside the safe set.
case "$POSTGRES_PASSWORD" in
    *[!A-Za-z0-9._~-]*)
        command -v python3 >/dev/null 2>&1 \
            || fail "POSTGRES_PASSWORD has special characters; install python3 or use openssl rand -hex 24"
        encoded="$(python3 -c 'import os, urllib.parse; print(urllib.parse.quote(os.environ["POSTGRES_PASSWORD"], safe=""))')"
        ;;
    *)
        encoded="$POSTGRES_PASSWORD"
        ;;
esac

umask 077
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT INT TERM

printf '%s' "$POSTGRES_PASSWORD" >"$work/POSTGRES_PASSWORD"
printf '%s' "postgresql+psycopg://attendflow:${encoded}@attendflow-db:5432/attendflow" \
    >"$work/DATABASE_URL"
printf '%s' "$ATTENDFLOW_SESSION_SECRET" >"$work/ATTENDFLOW_SESSION_SECRET"
printf '%s' "$ATTENDFLOW_DEMO_PASSWORD" >"$work/ATTENDFLOW_DEMO_PASSWORD"
unset encoded

set -- \
    --from-file=POSTGRES_PASSWORD="$work/POSTGRES_PASSWORD" \
    --from-file=DATABASE_URL="$work/DATABASE_URL" \
    --from-file=ATTENDFLOW_SESSION_SECRET="$work/ATTENDFLOW_SESSION_SECRET" \
    --from-file=ATTENDFLOW_DEMO_PASSWORD="$work/ATTENDFLOW_DEMO_PASSWORD"
if [ -n "${LLM_API_KEY:-}" ]; then
    printf '%s' "$LLM_API_KEY" >"$work/LLM_API_KEY"
    set -- "$@" --from-file=LLM_API_KEY="$work/LLM_API_KEY"
    llm_note="with the Groq key"
else
    llm_note="without a Groq key (template answers only)"
fi

kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl -n "$NAMESPACE" create secret generic attendflow-secrets "$@" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
echo "attendflow-secrets applied in namespace $NAMESPACE, $llm_note."

if [ -n "${GHCR_USERNAME:-}" ] && [ -n "${GHCR_TOKEN:-}" ]; then
    auth="$(printf '%s:%s' "$GHCR_USERNAME" "$GHCR_TOKEN" | base64 | tr -d '\n')"
    printf '{"auths":{"ghcr.io":{"auth":"%s"}}}' "$auth" >"$work/dockerconfig.json"
    unset auth
    kubectl -n "$NAMESPACE" create secret generic ghcr-pull \
        --type=kubernetes.io/dockerconfigjson \
        --from-file=.dockerconfigjson="$work/dockerconfig.json" \
        --dry-run=client -o yaml | kubectl apply -f - >/dev/null
    echo "ghcr-pull applied in namespace $NAMESPACE."
elif [ -n "${GHCR_USERNAME:-}${GHCR_TOKEN:-}" ]; then
    fail "set both GHCR_USERNAME and GHCR_TOKEN to create the image pull secret"
fi

echo "Restart the app to load changed values: kubectl -n $NAMESPACE rollout restart deploy/attendflow"

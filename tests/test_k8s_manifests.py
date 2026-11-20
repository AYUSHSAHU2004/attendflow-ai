"""Static checks for the Kubernetes manifests in deploy/k8s (Phase K1). No cluster needed."""

import re
import secrets
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from attendflow.config import get_settings

ROOT = Path(__file__).resolve().parents[1]
K8S = ROOT / "deploy" / "k8s"
SECRETS_SCRIPT = ROOT / "scripts" / "k8s-create-secrets.sh"
CI = ROOT / ".github" / "workflows" / "ci.yml"
ENV_EXAMPLE = ROOT / ".env.example"

# Example files that are applied by hand, never by `kubectl apply -k`.
EXAMPLES = {"auth.example.yaml", "cluster-issuers.example.yaml", "traefik-config.example.yaml"}
SECRET_KEYS = {
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "ATTENDFLOW_SESSION_SECRET",
    "ATTENDFLOW_DEMO_PASSWORD",
    "LLM_API_KEY",
}
# Not read by the app yet; kept in the ConfigMap so a later phase changes it in one place.
FUTURE_KEYS = {"ATTENDFLOW_SEED_PROFILE"}


def _docs(path: Path) -> list[dict]:
    return [doc for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")) if doc]


def _kustomization() -> dict:
    return _docs(K8S / "kustomization.yaml")[0]


def _resources() -> list[dict]:
    return [doc for name in _kustomization()["resources"] for doc in _docs(K8S / name)]


def _one(kind: str, name: str) -> dict:
    found = [d for d in _resources() if d["kind"] == kind and d["metadata"]["name"] == name]
    assert len(found) == 1, f"expected one {kind}/{name}, found {len(found)}"
    return found[0]


def _config() -> dict[str, str]:
    return _one("ConfigMap", "attendflow-config")["data"]


def _app_container() -> dict:
    spec = _one("Deployment", "attendflow")["spec"]["template"]["spec"]
    (container,) = spec["containers"]
    return container


# ------------------------------------------------------------------ kustomization


def test_kustomization_lists_every_manifest_and_no_example():
    kustomization = _kustomization()
    assert kustomization["namespace"] == "attendflow"
    listed = set(kustomization["resources"])
    on_disk = {p.name for p in K8S.glob("*.yaml")} - {"kustomization.yaml"}
    assert listed == on_disk - EXAMPLES
    assert not listed & EXAMPLES


def test_apply_never_carries_a_secret():
    # The real Secret comes from scripts/k8s-create-secrets.sh; a placeholder Secret in the
    # kustomization would overwrite it on every apply.
    assert not [d for d in _resources() if d["kind"] == "Secret"]


# ------------------------------------------------------------------ app Deployment


def test_app_runs_exactly_one_pod_and_recreates_on_rollout():
    deployment = _one("Deployment", "attendflow")
    assert deployment["spec"]["replicas"] == 1
    assert deployment["spec"]["strategy"] == {"type": "Recreate"}


def test_app_probes_use_healthz_on_the_container_port():
    container = _app_container()
    assert container["ports"] == [{"name": "http", "containerPort": 10000}]
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        get = container[probe]["httpGet"]
        assert get == {"path": "/healthz", "port": "http"}, probe
    # A database blip must not restart the pod at once (/healthz checks the database).
    liveness = container["livenessProbe"]
    assert liveness["periodSeconds"] * liveness["failureThreshold"] >= 60


def test_app_has_requests_and_limits_that_fit_a_4gb_node():
    def mebibytes(value: str) -> int:
        number, unit = re.fullmatch(r"(\d+)(Mi|Gi)", value).groups()
        return int(number) * (1024 if unit == "Gi" else 1)

    total_limit = 0
    for kind, name in (("Deployment", "attendflow"), ("StatefulSet", "attendflow-db")):
        for container in _one(kind, name)["spec"]["template"]["spec"]["containers"]:
            resources = container["resources"]
            assert set(resources) == {"requests", "limits"}
            assert {"cpu", "memory"} <= set(resources["requests"]) <= set(resources["limits"])
            total_limit += mebibytes(resources["limits"]["memory"])
    assert total_limit <= 1536  # leaves room for k3s, Traefik and cert-manager


def test_app_reads_config_and_only_its_own_secret_keys():
    container = _app_container()
    assert container["envFrom"] == [{"configMapRef": {"name": "attendflow-config"}}]
    refs = {
        item["name"]: item["valueFrom"]["secretKeyRef"]
        for item in container["env"]
        if "secretKeyRef" in item.get("valueFrom", {})
    }
    assert set(refs) == SECRET_KEYS - {"POSTGRES_PASSWORD"}
    assert {ref["name"] for ref in refs.values()} == {"attendflow-secrets"}
    assert all(name == ref["key"] for name, ref in refs.items())
    assert refs["LLM_API_KEY"].get("optional") is True


def test_app_pulls_the_private_ghcr_image_and_waits_for_the_database():
    spec = _one("Deployment", "attendflow")["spec"]["template"]["spec"]
    assert spec["imagePullSecrets"] == [{"name": "ghcr-pull"}]
    image = _app_container()["image"]
    assert re.fullmatch(r"ghcr\.io/[a-z0-9-]+/attendflow-ai:[a-z0-9.]+", image)
    (init,) = spec["initContainers"]
    assert "pg_isready -h attendflow-db" in " ".join(init["command"])
    # No ATTENDFLOW_* service variables injected by Kubernetes.
    assert spec["enableServiceLinks"] is False


# ------------------------------------------------------------------ Postgres


def test_postgres_has_one_pod_a_2gi_volume_a_readiness_check_and_a_clusterip_service():
    statefulset = _one("StatefulSet", "attendflow-db")
    assert statefulset["spec"]["replicas"] == 1
    (claim,) = statefulset["spec"]["volumeClaimTemplates"]
    assert claim["spec"]["resources"]["requests"]["storage"] == "2Gi"
    (container,) = statefulset["spec"]["template"]["spec"]["containers"]
    assert container["readinessProbe"]["exec"]["command"][0] == "pg_isready"
    assert container["livenessProbe"]["exec"]["command"][0] == "pg_isready"
    password = next(e for e in container["env"] if e["name"] == "POSTGRES_PASSWORD")
    assert password["valueFrom"]["secretKeyRef"]["name"] == "attendflow-secrets"
    service = _one("Service", "attendflow-db")
    assert service["spec"]["type"] == "ClusterIP"
    assert service["spec"]["ports"][0]["port"] == 5432
    assert statefulset["spec"]["serviceName"] == "attendflow-db"


# ------------------------------------------------------------------ ConfigMap


def test_configmap_is_the_locked_session_profile():
    config = _config()
    expected = {
        "ATTENDFLOW_DEPLOYED": "true",
        "ATTENDFLOW_AUTH_MODE": "session",
        "ATTENDFLOW_COOKIE_SECURE": "true",
        "ATTENDFLOW_TRUSTED_PROXY": "true",
        "LLM_DIAGNOSTICS": "off",
        "ATTENDFLOW_ENABLE_SEED": "false",
        "ATTENDFLOW_DEMO_MODE": "false",
        "ATTENDFLOW_DEMO_RESET_ENABLED": "false",
        "ATTENDFLOW_DEMO_EXTRA_WEEK": "false",
        "SCHEDULER_ENABLED": "false",
        "SCHEDULER_BACKLOG": "false",
        "ATTENDFLOW_SEED_PROFILE": "small",
    }
    assert {key: config.get(key) for key in expected} == expected
    assert "DEVICE_API_KEY" not in config
    assert "ATTENDFLOW_CORS_ORIGINS" not in config


def test_configmap_uses_env_example_names_and_holds_no_secret():
    config = _config()
    assert all(isinstance(value, str) for value in config.values())
    # Every NAME= in .env.example, including the commented profile lines.
    names = set(re.findall(r"\b([A-Z][A-Z0-9_]{2,})=", ENV_EXAMPLE.read_text("utf-8")))
    assert set(config) - FUTURE_KEYS <= names
    assert not set(config) & SECRET_KEYS
    assert not [k for k in config if re.search(r"SECRET|PASSWORD|_KEY$|TOKEN", k)]


def test_configmap_passes_the_deployed_settings_checks(monkeypatch):
    for key in list(_config()) + ["ATTENDFLOW_CORS_ORIGINS", "DEVICE_API_KEY", "LLM_API_KEY_FILE"]:
        monkeypatch.delenv(key, raising=False)
    for key, value in _config().items():
        monkeypatch.setenv(key, value)
    # Shaped like the values scripts/k8s-create-secrets.sh writes; generated per run.
    monkeypatch.setenv(
        "DATABASE_URL",
        f"postgresql+psycopg://attendflow:{secrets.token_hex(24)}@attendflow-db:5432/attendflow",
    )
    monkeypatch.setenv("ATTENDFLOW_SESSION_SECRET", secrets.token_hex(32))
    monkeypatch.setenv("ATTENDFLOW_DEMO_PASSWORD", secrets.token_hex(24))
    monkeypatch.setenv("LLM_API_KEY", secrets.token_hex(24))
    settings = get_settings(env_file=None)
    assert settings.deployed and settings.auth_mode == "session"
    assert settings.cookie_secure and settings.trusted_proxy
    assert not settings.llm_diagnostics and not settings.scheduler_enabled
    assert not settings.enable_seed and not settings.demo_mode
    assert settings.cors_origins == ()


# ------------------------------------------------------------------ Ingress + network


def test_ingress_uses_traefik_tls_cert_manager_and_an_sslip_host():
    ingress = _one("Ingress", "attendflow")
    spec = ingress["spec"]
    assert spec["ingressClassName"] == "traefik"
    (rule,) = spec["rules"]
    (tls,) = spec["tls"]
    assert rule["host"].endswith(".sslip.io") and tls["hosts"] == [rule["host"]]
    annotations = ingress["metadata"]["annotations"]
    assert annotations["cert-manager.io/cluster-issuer"] in {
        "letsencrypt-staging",
        "letsencrypt-prod",
    }
    middleware = _one("Middleware", "redirect-https")
    assert annotations["traefik.ingress.kubernetes.io/router.middlewares"] == (
        f"attendflow-{middleware['metadata']['name']}@kubernetescrd"
    )
    issuers = {d["metadata"]["name"] for d in _docs(K8S / "cluster-issuers.example.yaml")}
    assert issuers == {"letsencrypt-staging", "letsencrypt-prod"}


def test_only_traefik_reaches_the_app_and_only_the_app_reaches_postgres():
    deny = _one("NetworkPolicy", "default-deny-ingress")["spec"]
    assert deny == {"podSelector": {}, "policyTypes": ["Ingress"]}
    app = _one("NetworkPolicy", "app-from-traefik")["spec"]["ingress"]
    assert app[0]["from"][0]["podSelector"]["matchLabels"] == {"app.kubernetes.io/name": "traefik"}
    db = _one("NetworkPolicy", "db-from-app")["spec"]["ingress"]
    assert db[0]["from"][0]["podSelector"]["matchLabels"]["app.kubernetes.io/component"] == "app"


# ------------------------------------------------------------------ no real secrets


def test_secret_example_holds_only_empty_placeholders():
    (secret,) = _docs(K8S / "auth.example.yaml")
    assert secret["kind"] == "Secret"
    assert set(secret["stringData"]) == SECRET_KEYS
    assert set(secret["stringData"].values()) == {""}


@pytest.mark.parametrize(
    "path",
    sorted(K8S.glob("*.yaml")) + [SECRETS_SCRIPT],
    ids=lambda p: p.name,
)
def test_no_real_secret_values_in_deploy_files(path):
    text = path.read_text(encoding="utf-8")
    patterns = {
        "Groq key": r"gsk_[A-Za-z0-9]{20,}",
        "GitHub token": r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}",
        "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        "long random value": r"\b[A-Fa-f0-9]{32,}\b|\b[A-Za-z0-9+/]{40,}={0,2}",
        "password in a URL": r"://[^:/\s]+:(?!\$\{|<)[^@\s]+@",
    }
    for label, pattern in patterns.items():
        assert not re.search(pattern, text), f"{path.name}: looks like a {label}"


def test_secrets_script_never_puts_values_on_the_command_line_or_screen():
    script = SECRETS_SCRIPT.read_text(encoding="utf-8")
    assert "--from-literal" not in script
    assert "set -x" not in script
    for name in ("POSTGRES_PASSWORD", "ATTENDFLOW_SESSION_SECRET", "ATTENDFLOW_DEMO_PASSWORD"):
        assert not re.search(rf"echo[^\n]*\${{?{name}", script)
    assert "kubectl apply -f - >/dev/null" in script


# ------------------------------------------------------------------ CI image job


def test_ci_pushes_the_image_from_main_only_after_the_tests():
    workflow = yaml.safe_load(CI.read_text(encoding="utf-8"))
    job = workflow["jobs"]["image"]
    assert job["needs"] == "backend"
    assert job["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    assert job["permissions"] == {"contents": "read", "packages": "write"}
    build = next(s for s in job["steps"] if "build-push-action" in s.get("uses", ""))
    assert build["with"]["platforms"] == "linux/amd64"
    tags = build["with"]["tags"]
    assert "${{ github.sha }}" in tags and ":latest" in tags
    text = CI.read_text(encoding="utf-8")
    assert "secrets.GITHUB_TOKEN" in text
    assert not re.search(r"secrets\.(?!GITHUB_TOKEN\b)", text)


# ------------------------------------------------------------------ offline render


@pytest.mark.skipif(shutil.which("kubectl") is None, reason="kubectl not installed")
def test_kustomize_renders_offline_into_the_attendflow_namespace():
    result = subprocess.run(
        ["kubectl", "kustomize", str(K8S)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    rendered = [d for d in yaml.safe_load_all(result.stdout) if d]
    kinds = sorted(d["kind"] for d in rendered)
    assert kinds == sorted(
        [
            "ConfigMap",
            "Deployment",
            "Ingress",
            "Middleware",
            "Namespace",
            "NetworkPolicy",
            "NetworkPolicy",
            "NetworkPolicy",
            "NetworkPolicy",
            "Service",
            "Service",
            "StatefulSet",
        ]
    )
    for doc in rendered:
        if doc["kind"] != "Namespace":
            assert doc["metadata"]["namespace"] == "attendflow", doc["metadata"]["name"]
        assert doc["metadata"]["labels"]["app.kubernetes.io/part-of"] == "attendflow"

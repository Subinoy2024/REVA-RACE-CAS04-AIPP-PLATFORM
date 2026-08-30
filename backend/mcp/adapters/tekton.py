"""Tekton MCP adapter — Kubernetes CRDs under `tekton.dev/v1`.

Reuses the K8s kubeconfig for auth (Tekton is deployed inside a K8s cluster).
"""

from __future__ import annotations

import asyncio

from backend.core.config import get_settings
from backend.mcp.adapters.base import BaseMCPAdapter


class TektonAdapter(BaseMCPAdapter):
    name = "tekton"

    def is_configured(self) -> bool:
        import os
        s = get_settings()
        return bool(s.kubeconfig_path and os.path.exists(s.kubeconfig_path))

    def _register_tools(self) -> None:
        self._register("list_pipelines", self._list_pipelines)
        self._register("trigger_pipeline", self._trigger_pipeline)

    def _load(self):
        from kubernetes import config
        config.load_kube_config(config_file=get_settings().kubeconfig_path)

    async def _list_pipelines(self, *, namespace: str = "default") -> list[dict]:
        def _work():
            from kubernetes import client
            self._load()
            api = client.CustomObjectsApi()
            resp = api.list_namespaced_custom_object("tekton.dev", "v1", namespace, "pipelines")
            return [
                {"name": p["metadata"]["name"], "tasks": [t["name"] for t in p.get("spec", {}).get("tasks", [])]}
                for p in resp.get("items", [])
            ]
        return await asyncio.to_thread(_work)

    async def _trigger_pipeline(self, *, namespace: str, pipeline_name: str, run_name: str) -> dict:
        def _work():
            from kubernetes import client
            self._load()
            api = client.CustomObjectsApi()
            body = {
                "apiVersion": "tekton.dev/v1",
                "kind": "PipelineRun",
                "metadata": {"name": run_name, "namespace": namespace},
                "spec": {"pipelineRef": {"name": pipeline_name}},
            }
            return api.create_namespaced_custom_object(
                "tekton.dev", "v1", namespace, "pipelineruns", body,
            )
        return await asyncio.to_thread(_work)

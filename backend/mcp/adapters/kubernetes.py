"""Kubernetes MCP adapter — via the official kubernetes-client.

Config env vars:
  KUBECONFIG      path to a kubeconfig file (standard k8s convention)
"""

from __future__ import annotations

import asyncio
from typing import Any

from backend.core.config import get_settings
from backend.mcp.adapters.base import BaseMCPAdapter


class KubernetesAdapter(BaseMCPAdapter):
    name = "kubernetes"

    def is_configured(self) -> bool:
        import os
        s = get_settings()
        return bool(s.kubeconfig_path and os.path.exists(s.kubeconfig_path))

    def _register_tools(self) -> None:
        self._register("list_namespaces", self._list_namespaces)
        self._register("list_deployments", self._list_deployments)

    def _load(self):
        from kubernetes import config
        config.load_kube_config(config_file=get_settings().kubeconfig_path)

    async def _list_namespaces(self) -> list[str]:
        def _work():
            from kubernetes import client
            self._load()
            v1 = client.CoreV1Api()
            return [ns.metadata.name for ns in v1.list_namespace().items]
        return await asyncio.to_thread(_work)

    async def _list_deployments(self, *, namespace: str = "default") -> list[dict]:
        def _work():
            from kubernetes import client
            self._load()
            apps = client.AppsV1Api()
            out: list[dict] = []
            for d in apps.list_namespaced_deployment(namespace).items:
                out.append({
                    "name": d.metadata.name,
                    "namespace": d.metadata.namespace,
                    "replicas": d.spec.replicas,
                    "available": d.status.available_replicas,
                    "image": d.spec.template.spec.containers[0].image if d.spec.template.spec.containers else None,
                })
            return out
        return await asyncio.to_thread(_work)

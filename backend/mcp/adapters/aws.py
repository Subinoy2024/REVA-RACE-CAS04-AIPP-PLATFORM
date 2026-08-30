"""AWS MCP adapter — boto3.

Config env vars:
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_REGION           default us-east-1
"""

from __future__ import annotations

import asyncio

from backend.core.config import get_settings
from backend.mcp.adapters.base import BaseMCPAdapter


class AWSAdapter(BaseMCPAdapter):
    name = "aws"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.aws_access_key_id and s.aws_secret_access_key)

    def _register_tools(self) -> None:
        self._register("list_stacks", self._list_stacks)
        self._register("deploy_cloudformation", self._deploy_cloudformation)

    def _session(self):
        import boto3
        s = get_settings()
        return boto3.session.Session(
            aws_access_key_id=s.aws_access_key_id,
            aws_secret_access_key=s.aws_secret_access_key,
            region_name=s.aws_region,
        )

    async def _list_stacks(self) -> list[dict]:
        def _work():
            cf = self._session().client("cloudformation")
            resp = cf.list_stacks(StackStatusFilter=["CREATE_COMPLETE", "UPDATE_COMPLETE", "ROLLBACK_COMPLETE"])
            return [
                {"name": s["StackName"], "status": s["StackStatus"], "created": s["CreationTime"].isoformat()}
                for s in resp.get("StackSummaries", [])
            ]
        return await asyncio.to_thread(_work)

    async def _deploy_cloudformation(self, *, stack_name: str, template_body: str, parameters: list | None = None) -> dict:
        def _work():
            cf = self._session().client("cloudformation")
            return cf.create_stack(
                StackName=stack_name, TemplateBody=template_body,
                Parameters=parameters or [], Capabilities=["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"],
            )
        return await asyncio.to_thread(_work)

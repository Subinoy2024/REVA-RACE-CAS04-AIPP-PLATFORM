#!/usr/bin/env bash
# ==============================================================================
# AIPP · Push n8n Variables  ─ DEPRECATED (iteration-35)
# ==============================================================================
# This script pushed config into n8n's Variables API. That API is an
# ENTERPRISE-only feature — n8n Community edition rejects it with
# `feat:variables license error`.
#
# Iteration-35 refactor:
#   • build_workflows.py now reads n8n/.env.n8n at BUILD TIME
#   • Config values are inlined into each workflow JSON
#   • Zero dependency on the Variables API → works on Community edition
#
# Migration:
#   OLD FLOW:  edit .env.n8n → push_variables.sh → deploy.sh
#   NEW FLOW:  edit .env.n8n → python3 build_workflows.py → scripts/deploy.sh
# ==============================================================================
set -euo pipefail

cat <<'BANNER'
================================================================
  push_variables.sh is deprecated (iteration-35).

  n8n Community edition does not support the Variables API.
  Config is now inlined into workflow JSONs at build time.

  Run this instead:
      cd n8n
      python3 build_workflows.py     # regenerate workflows with your config
      bash scripts/deploy.sh         # push them to n8n
================================================================
BANNER
exit 0

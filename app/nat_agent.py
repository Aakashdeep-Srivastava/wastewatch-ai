# app/nat_agent.py
# -----------------------------------------------------------------------------
# OPTIONAL: NVIDIA NeMo Agent Toolkit (NAT) orchestration wrapper.
#
# This exposes WasteWatch's Nemotron intelligence-brief step as a registered NAT
# *function*, so the reasoning step can be driven by NVIDIA's open-source agentic
# framework and composed with other NAT tools / MCP servers (see nat_config.yml).
#
# IMPORTANT (honesty): NeMo Agent Toolkit was deprecated by NVIDIA in Oct 2026.
# WasteWatch therefore treats NAT as an OPTIONAL wrapper. The authoritative,
# always-on path is the direct Nemotron call in app/nemotron.py — identical
# logic. This module is imported ONLY by the `nat` CLI, never by the web app, and
# the whole thing is guarded so a missing/renamed NAT API can never break
# WasteWatch. If nvidia-nat is not installed, NAT_AVAILABLE is False and nothing
# else here is defined.
# -----------------------------------------------------------------------------
try:
    from pydantic import Field
    from nat.builder.builder import Builder
    from nat.builder.function_info import FunctionInfo
    from nat.cli.register_workflow import register_function
    from nat.data_models.function import FunctionBaseConfig
    NAT_AVAILABLE = True
except Exception:                                   # noqa: BLE001
    NAT_AVAILABLE = False


if NAT_AVAILABLE:
    from . import nemotron

    class WasteWatchBriefConfig(FunctionBaseConfig, name="wastewatch_brief"):
        """Fuse CV metrics + open environmental data into a regulator-ready brief
        using NVIDIA Nemotron on Nebius Token Factory."""
        deep: bool = Field(
            default=False,
            description="Use the Ultra reasoning model for high-severity cases.")

    @register_function(config_type=WasteWatchBriefConfig)
    async def wastewatch_brief(config: WasteWatchBriefConfig, builder: Builder):
        async def _run(context_json: str) -> str:
            """context_json: JSON with change_score, disturbed_surface, vlm,
            enrichment, location, dates. Returns the brief as JSON text."""
            import json
            try:
                ctx = json.loads(context_json)
            except Exception:                       # noqa: BLE001
                ctx = {"raw": context_json}
            brief = nemotron.intelligence_brief(ctx, deep=config.deep)
            return json.dumps(brief or {"error": "nemotron unavailable"})

        yield FunctionInfo.from_fn(
            _run,
            description="WasteWatch environmental intelligence brief "
                        "(NVIDIA Nemotron on Nebius Token Factory).")

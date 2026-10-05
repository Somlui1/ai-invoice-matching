"""Settings + composition root.  Secrets only from environment (never defaults with real hosts)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from .adapters.llm.simulators import FailingAI, SimEntityJudge, SimLineMatcher, SimQtyJudge
from .adapters.oracle.repositories import InMemoryOracleRepository, OracleDbRepository
from .application.orchestrator import Services
from .domain.standard import load_standard
from .envfile import load_env


@dataclass(frozen=True)
class Settings:
    mode: str = os.getenv("SYSTEM_A_MODE", "sandbox")            # sandbox | production
    ai_mode: str = os.getenv("SYSTEM_A_AI_MODE", "sim")           # sim | litellm
    api_key: str = os.getenv("SYSTEM_A_API_KEY", "")              # empty = auth disabled (sandbox only)
    litellm_url: str = os.getenv("LITELLM_URL", "")
    litellm_key: str = os.getenv("LITELLM_API_KEY", "")
    model_reasoning: str = os.getenv("MODEL_REASONING", "qwen3-reasoning")
    model_vision: str = os.getenv("MODEL_VISION", "qwen-vl")
    oracle_backend: str = os.getenv("ORACLE_BACKEND", "mcp")      # mcp (ORDS MCP) | db (python-oracledb)
    oracle_mcp_url: str = os.getenv("ORACLE_MCP_URL", "")
    oracle_mcp_token: str = os.getenv("ORACLE_MCP_TOKEN", "")
    oracle_database: str = os.getenv("ORACLE_DATABASE", "default")
    oracle_dsn: str = os.getenv("ORACLE_DSN", "")
    oracle_user: str = os.getenv("ORACLE_USER", "")
    oracle_password: str = os.getenv("ORACLE_PASSWORD", "")
    oracle_timeout_s: float = float(os.getenv("ORACLE_TIMEOUT_SECONDS", "60"))
    result_ttl_s: int = int(os.getenv("RESULT_TTL_SECONDS", str(24 * 3600)))   # OQ-10
    paperless_url: str = os.getenv("PAPERLESS_BASE_URL", "")
    paperless_token: str = os.getenv("PAPERLESS_API_TOKEN", "")
    paperless_timeout_s: float = float(os.getenv("PAPERLESS_TIMEOUT_SECONDS", "120"))
    render_dpi: int = int(os.getenv("PERCEPTION_DPI", "150"))
    crop_dpi: int = int(os.getenv("PERCEPTION_CROP_DPI", "300"))
    max_pages: int = int(os.getenv("PERCEPTION_MAX_PAGES", "12"))
    coord_mode: str = os.getenv("PERCEPTION_COORD", "auto")                  # auto | pixel | norm1000 | norm1
    do_table: bool = os.getenv("PERCEPTION_TABLE", "1") == "1"
    do_crops: bool = os.getenv("PERCEPTION_CROPS", "1") == "1"
    do_classify: bool = os.getenv("PERCEPTION_CLASSIFY", "1") == "1"
    json_mode: bool = os.getenv("PERCEPTION_JSON_MODE", "1") == "1"
    perception_cache: str = os.getenv("PERCEPTION_CACHE_DIR", ".cache/perception")
    llm_timeout_s: float = float(os.getenv("LITELLM_TIMEOUT_SECONDS", "300"))
    llm_max_inflight: int = int(os.getenv("LITELLM_MAX_INFLIGHT", "6"))


def build_services(settings: Settings, *, oracle_dataset: dict | None = None, oracle_down: bool = False,
                   ai: str | None = None) -> Services:
    if settings.mode == "production":
        std = load_standard()
        row_cap = std.policy["oracle"]["row_cap"]
        if settings.oracle_backend == "db":
            oracle = OracleDbRepository(settings.oracle_dsn, settings.oracle_user, settings.oracle_password)
        else:
            from .adapters.oracle.mcp_repository import McpSqlClient, OracleMcpRepository
            if not settings.oracle_mcp_url:
                raise RuntimeError("ORACLE_MCP_URL is required when SYSTEM_A_MODE=production")
            client = McpSqlClient(settings.oracle_mcp_url, settings.oracle_mcp_token,
                                  timeout_s=settings.oracle_timeout_s)
            oracle = OracleMcpRepository(client, row_cap=row_cap, database=settings.oracle_database)
    else:
        oracle = InMemoryOracleRepository(oracle_dataset or {}, down=oracle_down)
    ai = ai or settings.ai_mode
    if ai == "litellm":
        from .adapters.llm.ai_services import LiteLLMEntityJudge, LiteLLMLineMatcher, LiteLLMQtyJudge
        from .adapters.llm.litellm_client import LiteLLMClient
        # Rule calls (V-07 matcher, V-08 3 votes) are reasoning-heavy: on the real gateway a single
        # thinking call measured 10-40 s, so the 120 s client default is too tight when several
        # documents share the in-flight budget.  Measured need -> configurable, default 300 s.
        c = LiteLLMClient(settings.litellm_url, settings.litellm_key,
                          timeout_s=settings.llm_timeout_s, max_inflight=settings.llm_max_inflight)
        return Services(oracle, LiteLLMLineMatcher(c, settings.model_reasoning), LiteLLMQtyJudge(c, settings.model_reasoning),
                        LiteLLMEntityJudge(c, settings.model_reasoning),
                        models={"line_matcher": settings.model_reasoning, "qty_judge": settings.model_reasoning,
                                "entity_judge": settings.model_reasoning, "vision": settings.model_vision})
    sim_models = {"line_matcher": "sim-v07@1", "qty_judge": "sim-v08@1", "entity_judge": "sim-v05@1"}
    if ai == "down":
        f = FailingAI()
        return Services(oracle, f, f, f, models=sim_models)
    return Services(oracle, SimLineMatcher(), SimQtyJudge(faulty=(ai == "faulty_qty")), SimEntityJudge(),
                    models=sim_models)


def build_paperless(settings: Settings):
    """Read-only DMS client.  Nothing in System A ever writes back to Paperless-ngx."""
    from .adapters.paperless.reader import PaperlessReader
    if not settings.paperless_url:
        raise RuntimeError("PAPERLESS_BASE_URL is required to read real DMS documents")
    return PaperlessReader(settings.paperless_url, settings.paperless_token, timeout_s=settings.paperless_timeout_s)


def build_perception(settings: Settings, client=None):
    """Real perception (Qwen page-items + PDF text layer).  Uses the same LiteLLM endpoint as the AI rules."""
    from .perception.vision_pipeline import VisionPipeline
    if client is None:
        from .adapters.llm.litellm_client import LiteLLMClient
        if not settings.litellm_url:
            raise RuntimeError("LITELLM_URL is required for real perception")
        client = LiteLLMClient(settings.litellm_url, settings.litellm_key, timeout_s=600, max_inflight=8)
    return VisionPipeline(client, settings.model_vision, dpi=settings.render_dpi, crop_dpi=settings.crop_dpi,
                          coord=settings.coord_mode, max_pages=settings.max_pages, do_table=settings.do_table,
                          do_crops=settings.do_crops, do_classify=settings.do_classify,
                          json_mode=settings.json_mode)


def perception_options(settings: Settings) -> dict:
    """The options that change a perception answer — part of the cache key."""
    return {"dpi": settings.render_dpi, "crop_dpi": settings.crop_dpi, "max_pages": settings.max_pages,
            "coord": settings.coord_mode, "table": settings.do_table, "crops": settings.do_crops,
            "classify": settings.do_classify, "json_mode": settings.json_mode}

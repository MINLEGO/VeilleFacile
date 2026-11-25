import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SUMMARY_MODEL = (
    "nvidia/nemotron-3.5-lightning:free,nvidia/nemotron-3.5-super-vl:free,"
    "google/gemma-4-26b-a4b-it:free,nvidia/nemotron-3.5-lightning"
)


@dataclass(frozen=True)
class Settings:
    api_key: str
    database_url: str
    openrouter_api_key: str = ""
    github_token: str = ""
    hf_token: str = ""
    mcp_disabled_tools: str = "update_source,delete_source"
    embedding_model: str = "nvidia/nemotron-3.5-embed-8b:free"
    summary_model: str = DEFAULT_SUMMARY_MODEL
    migrations_dir: str = str(Path(__file__).parent / "migrations")
    skip_migrations: bool = False  # tests only
    skip_model_check: bool = False  # tests only: no OpenRouter model list lookup at startup

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ
        d = cls(api_key="", database_url="")
        return cls(
            api_key=e["API_KEY"],
            database_url=e["DATABASE_URL"],
            openrouter_api_key=e.get("OPENROUTER_API_KEY", ""),
            github_token=e.get("GITHUB_TOKEN", ""),
            hf_token=e.get("HF_TOKEN", ""),
            mcp_disabled_tools=e.get("MCP_DISABLED_TOOLS", d.mcp_disabled_tools),
            embedding_model=e.get("EMBEDDING_MODEL", d.embedding_model),
            summary_model=e.get("SUMMARY_MODEL", d.summary_model),
        )

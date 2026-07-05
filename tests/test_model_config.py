"""Tests for the model factory (add-multi-model-support)."""
from __future__ import annotations

import os
from pathlib import Path
import sys

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

from agents import _model  # noqa: E402


@pytest.fixture
def clean_env(monkeypatch):
    """Strip every TRIAGE_* / provider key so each test starts from a blank slate."""
    for key in (
        "TRIAGE_MODEL_PROVIDER",
        "TRIAGE_MODEL",
        "TRIAGE_API_BASE",
        "TRIAGE_API_KEY",
        "ZHIPUAI_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


class TestBuildModel:
    def test_build_model_defaults_to_gemini(self, clean_env):
        assert _model.build_model() == "gemini-2.5-flash"

    def test_build_model_gemini_custom_model(self, clean_env, monkeypatch):
        monkeypatch.setenv("TRIAGE_MODEL_PROVIDER", "gemini")
        monkeypatch.setenv("TRIAGE_MODEL", "gemini-2.5-pro")
        assert _model.build_model() == "gemini-2.5-pro"

    def test_build_model_openai_compat_returns_litellm(self, clean_env, monkeypatch):
        from google.adk.models.lite_llm import LiteLlm

        monkeypatch.setenv("TRIAGE_MODEL_PROVIDER", "openai_compat")
        monkeypatch.setenv("TRIAGE_MODEL", "glm-5.2")
        monkeypatch.setenv("TRIAGE_API_BASE", "https://example/api")
        monkeypatch.setenv("TRIAGE_API_KEY", "sk-test")

        m = _model.build_model()
        assert isinstance(m, LiteLlm)
        assert m.model == "openai/glm-5.2"
        assert m._additional_args["api_base"] == "https://example/api"
        assert m._additional_args["api_key"] == "sk-test"

    def test_build_model_openai_compat_keeps_prefixed_model(self, clean_env, monkeypatch):
        monkeypatch.setenv("TRIAGE_MODEL_PROVIDER", "openai_compat")
        monkeypatch.setenv("TRIAGE_MODEL", "openai/gpt-4o")
        monkeypatch.setenv("TRIAGE_API_BASE", "https://example/api")
        monkeypatch.setenv("TRIAGE_API_KEY", "sk-test")
        assert _model.build_model().model == "openai/gpt-4o"

    def test_build_model_openai_compat_accepts_alias_key(self, clean_env, monkeypatch):
        monkeypatch.setenv("TRIAGE_MODEL_PROVIDER", "openai_compat")
        monkeypatch.setenv("TRIAGE_MODEL", "glm-5.2")
        monkeypatch.setenv("TRIAGE_API_BASE", "https://example/api")
        monkeypatch.setenv("ZHIPUAI_API_KEY", "zhipu-key")
        m = _model.build_model()
        assert m._additional_args["api_key"] == "zhipu-key"

    def test_build_model_incomplete_openai_compat_falls_back(self, clean_env, monkeypatch):
        # openai_compat requested but TRIAGE_API_BASE missing -> import-safe fallback
        monkeypatch.setenv("TRIAGE_MODEL_PROVIDER", "openai_compat")
        monkeypatch.setenv("TRIAGE_MODEL", "glm-5.2")
        monkeypatch.setenv("TRIAGE_API_KEY", "sk-test")
        assert _model.build_model() == "gemini-2.5-flash"


class TestHasModelKey:
    def test_has_model_key_gemini_present(self, clean_env, monkeypatch):
        monkeypatch.setenv("TRIAGE_MODEL_PROVIDER", "gemini")
        monkeypatch.setenv("GOOGLE_API_KEY", "g-key")
        assert _model._has_model_key() is True

    def test_has_model_key_openai_compat_present(self, clean_env, monkeypatch):
        monkeypatch.setenv("TRIAGE_MODEL_PROVIDER", "openai_compat")
        monkeypatch.setenv("TRIAGE_MODEL", "glm-5.2")
        monkeypatch.setenv("TRIAGE_API_BASE", "https://example/api")
        monkeypatch.setenv("TRIAGE_API_KEY", "sk-test")
        assert _model._has_model_key() is True

    def test_has_model_key_missing_returns_false(self, clean_env, monkeypatch):
        monkeypatch.setenv("TRIAGE_MODEL_PROVIDER", "gemini")
        assert _model._has_model_key() is False

    def test_has_model_key_openai_compat_missing_returns_false(self, clean_env, monkeypatch):
        # openai_compat requested but nothing configured -> resolves to gemini -> no gemini key -> False
        monkeypatch.setenv("TRIAGE_MODEL_PROVIDER", "openai_compat")
        assert _model._has_model_key() is False


class TestCurrentProvider:
    def test_current_provider_defaults_to_gemini(self, clean_env):
        assert _model.current_provider() == "gemini"

    def test_current_provider_reads_env(self, clean_env, monkeypatch):
        monkeypatch.setenv("TRIAGE_MODEL_PROVIDER", "openai_compat")
        assert _model.current_provider() == "openai_compat"

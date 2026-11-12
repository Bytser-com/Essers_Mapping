"""Shared pytest fixtures for all tests (e.g. paths to tests/fixtures, a fake Gemini).

Tests must never call the real Gemini API and must not depend on ai_tool/data/,
which is not in Git. Use the small example files in tests/fixtures/ instead.
"""

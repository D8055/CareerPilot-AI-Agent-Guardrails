"""Pydantic models for the API surface."""
from pydantic import BaseModel, Field


class TailorRequest(BaseModel):
    jd_text: str = Field(min_length=1, description="Job description text")


class TailorReport(BaseModel):
    match_score: int | None
    matched_keywords: list[str]
    missing_keywords: list[str]
    plan: dict
    plan_source: str = "deterministic"
    honesty_violations: list[str] = []

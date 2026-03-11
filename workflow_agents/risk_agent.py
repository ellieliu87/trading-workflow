from agents import Agent
from skills import SkillLoader


def build_risk_agent() -> Agent:
    return SkillLoader.load("risk_agent").build()

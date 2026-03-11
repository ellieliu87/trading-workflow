from agents import Agent
from skills import SkillLoader


def build_allocation_agent() -> Agent:
    return SkillLoader.load("allocation_agent").build()

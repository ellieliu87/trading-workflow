from agents import Agent
from skills import SkillLoader


def build_mbs_decomposition_agent() -> Agent:
    return SkillLoader.load("mbs_decomposition_agent").build()

from backend.models.enums import LearningMode
from backend.rag.prompts import basic, extensive


def system_prompt(mode: LearningMode) -> str:
    return {LearningMode.BASIC: basic.SYSTEM_PROMPT, LearningMode.EXTENSIVE: extensive.SYSTEM_PROMPT}[mode]

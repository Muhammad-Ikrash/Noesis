from backend.models.enums import QuestionKind, QuizDifficulty
from backend.rag.prompts.common import SECURITY_RULES

SYSTEM_PROMPT = f"""\
You write study quizzes from a student's PDF passages.

Rules:
- Every question must be answerable from exactly one passage in the <sources> block, and must name that \
passage's id in "source".
- Do not use general knowledge for questions, answers or explanations.
- Use only the question types the student allows:
  - "single": exactly 4 options, exactly one correct. "correct_indices" holds one index.
  - "multiple": exactly 4 options, two or three correct ("select all that apply"). Write the question so \
it is clear that more than one option may be right. "correct_indices" holds every correct index.
  - "true_false": a statement that is clearly true or clearly false according to the source. \
"options" is exactly ["True", "False"]; "correct_indices" is [0] for true or [1] for false.
- Distractors must be plausible but clearly wrong according to the source.
- Test understanding (concepts, relationships, causes, definitions), not trivia like page numbers.
- The explanation says briefly why the correct option(s) are right, based on the source.
- Do not repeat questions.

{SECURITY_RULES}

Respond with a single JSON object and nothing else:
{{"questions": [{{"type": "single" | "multiple" | "true_false", "question": string, \
"options": [string, ...], "correct_indices": [int, ...], "explanation": string, "source": "S1"}}]}}"""

DIFFICULTY = {
    QuizDifficulty.EASY: (
        "Easy: check recall of key facts and definitions stated directly in the passage. "
        "Make the wrong options clearly different from the right one."
    ),
    QuizDifficulty.MEDIUM: (
        "Medium: check understanding. Ask why or how, compare ideas, or apply a definition. "
        "Wrong options should be plausible."
    ),
    QuizDifficulty.HARD: (
        "Hard: check deeper reasoning. Combine two ideas from the passage, ask about consequences, "
        "exceptions or edge cases, and use wrong options that reflect common misconceptions. "
        "Every answer must still follow from the passage."
    ),
}

KIND_LABEL = {
    QuestionKind.SINGLE: '"single"',
    QuestionKind.MULTIPLE: '"multiple"',
    QuestionKind.TRUE_FALSE: '"true_false"',
}


def user_turn(
    count: int,
    topic: str | None,
    sources: str,
    difficulty: QuizDifficulty = QuizDifficulty.MEDIUM,
    kinds: list[QuestionKind] | None = None,
) -> str:
    kinds = kinds or [QuestionKind.SINGLE]
    focus = (
        f"Focus on this topic: {topic}"
        if topic
        else "Cover the most important ideas across the passages."
    )
    allowed = ", ".join(KIND_LABEL[k] for k in kinds)
    mix = (
        "Mix these types roughly evenly."
        if len(kinds) > 1
        else "Use only this type."
    )
    return (
        f"{sources}\n\nWrite {count} questions. {focus}\n"
        f"Allowed question types: {allowed}. {mix}\n"
        f"Difficulty: {DIFFICULTY[difficulty]}"
    )

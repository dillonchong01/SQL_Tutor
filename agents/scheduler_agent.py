"""SchedulerAgent: SM-2 spaced repetition scheduling and weak-topic question generation."""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class SM2State:
    easiness: float = 2.5
    interval: int = 1
    repetitions: int = 0


class SchedulerAgent:
    def __init__(self, llm):
        self.llm = llm
        self.sm2 = {}

    def schedule_next(self, question_id, quality):
        state = self.sm2.get(question_id, SM2State())
        quality = max(0, min(5, quality))

        if quality < 3:
            state.repetitions = 0
            state.interval = 1
        else:
            if state.repetitions == 0:
                state.interval = 1
            elif state.repetitions == 1:
                state.interval = 6
            else:
                state.interval = int(round(state.interval * state.easiness))
            state.repetitions += 1

        state.easiness = max(
            1.3,
            state.easiness + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)),
        )
        self.sm2[question_id] = state
        return (date.today() + timedelta(days=state.interval)).isoformat()

    async def generate_question_for_topic(self, topic, difficulty="medium"):
        system = (
            "You are an assessment generator. Return JSON with one key question containing question_text, "
            "table_schema, sample_data, hidden_test_cases, topic_tags, difficulty, expected_query."
        )
        user = f"Create one SQL practice problem focused on topic={topic} with difficulty={difficulty}."
        payload = await self.llm.generate_json(system, user)
        question = payload["question"]
        question["question_id"] = str(uuid.uuid4())
        return question

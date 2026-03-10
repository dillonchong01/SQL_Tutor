"""AssessmentAgent: generates an initial personalized SQL assessment."""

from llm_helpers import LLMClient


class AssessmentAgent:
    def __init__(self, llm):
        self.llm = llm

    async def generate_initial_assessment(self, learner_profile, num_questions=5):
        system = (
            "You are an expert SQL tutor. Return ONLY JSON with key 'questions'. "
            "Each question must include: question_text, table_schema, sample_data, hidden_test_cases, "
            "topic_tags (list), difficulty (easy|medium|hard), expected_query."
        )
        user = (
            f"Generate {num_questions} assessment questions for this learner profile: {learner_profile}. "
            "Design realistic business datasets and include hidden test data distinct from sample data."
        )
        data = await self.llm.generate_json(system, user)
        return data["questions"]

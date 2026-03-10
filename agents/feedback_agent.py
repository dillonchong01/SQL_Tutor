"""FeedbackAgent: provides Socratic hints without revealing direct answers."""


class FeedbackAgent:
    def __init__(self, llm):
        self.llm = llm

    async def generate_hint(self, question, student_sql):
        system = (
            "You are a Socratic SQL tutor. Never provide the full answer query. "
            "Give progressive hints: conceptual issue, then one concrete next step."
        )
        user = (
            f"Question: {question['question_text']}\n"
            f"Schema: {question['table_schema']}\n"
            f"Student SQL: {student_sql}\n"
            "Offer a concise hint and one reflective question."
        )
        return await self.llm.generate_text(system, user)

"""AnalyticsAgent: updates confidence scores in the knowledge map."""


class AnalyticsAgent:
    def __init__(self, store):
        self.store = store

    def update_after_attempt(self, user_id, topics, passed_hidden):
        knowledge = {item["topic"]: item["confidence_score"] for item in self.store.get_knowledge_map(user_id)}
        delta = 0.08 if passed_hidden else -0.05
        for topic in topics:
            current = knowledge.get(topic, 0.5)
            updated = min(1.0, max(0.0, current + delta))
            self.store.update_knowledge(user_id, topic, updated)

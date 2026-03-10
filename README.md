# Agentic SQL Tutor

Chainlit + LangGraph SQL tutoring app with multi-agent architecture:
- `AssessmentAgent` for assessment generation
- `FeedbackAgent` for Socratic hints
- `AnalyticsAgent` for per-topic confidence
- `SchedulerAgent` with SM-2 scheduling

## Runtime dependencies
- Python 3.10+
- Python libraries from `requirements.txt`
- No external database server is required

## Agentic architecture
- Uses **LangChain** (`ChatOpenAI`) for LLM access and prompting.
- Uses **LangGraph** state graphs to orchestrate:
  - onboarding flow (user load -> assessment generation -> pending selection)
  - hidden-test evaluation flow (student execution -> expected execution -> evaluation -> analytics/schedule updates)

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
chainlit run app.py
```

## Storage and SQL execution
- SQLite local DB for users, questions, knowledge map, and study plan.
- Student SQL is executed in an isolated in-memory SQLite sandbox per run.

## Notes
- Hidden test validation compares student output with model-generated `expected_query` output.
- SQL sandbox permits `SELECT` only and enforces timeout checks.

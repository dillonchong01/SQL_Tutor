"""Chainlit application for an agentic SQL tutor using LangGraph orchestration."""

import json
import logging
import os
import uuid

import chainlit as cl
import plotly.graph_objects as go
from langgraph.graph import END, START, StateGraph

from agents import AnalyticsAgent, AssessmentAgent, FeedbackAgent, SchedulerAgent
from database.mysql_sandbox import MySQLSandbox, SQLSandboxError
from database.sqlite_store import SQLiteStore
from llm_helpers import LLMClient

logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger(__name__)

store = SQLiteStore(db_path=os.getenv("SQLITE_DB_PATH", "data/sql_tutor.db"))
llm = LLMClient()
assessment_agent = AssessmentAgent(llm)
scheduler_agent = SchedulerAgent(llm)
feedback_agent = FeedbackAgent(llm)
analytics_agent = AnalyticsAgent(store)
sandbox = MySQLSandbox()


def get_current_question():
    return cl.user_session.get("current_question")


def set_current_question(question):
    cl.user_session.set("current_question", question)


async def render_analytics(user_id):
    knowledge = store.get_knowledge_map(user_id)
    if knowledge:
        topics = [item["topic"] for item in knowledge]
        scores = [item["confidence_score"] for item in knowledge]
        fig = go.Figure(data=[go.Bar(x=topics, y=scores)])
        fig.update_layout(title="Knowledge Map", yaxis_range=[0, 1])
        await cl.Message(
            content="Updated knowledge map:",
            elements=[cl.Plotly(name="knowledge_map", figure=fig, display="inline")],
        ).send()

    plan = store.get_study_plan(user_id)
    if plan:
        timeline = "\n".join(
            [f"- {item.scheduled_date}: {item.question_id} ({'done' if item.completed else 'pending'})" for item in plan]
        )
        await cl.Message(content=f"### Study Plan\n{timeline}").send()


async def send_question(question):
    set_current_question(question)
    content = (
        f"### Question\n{question['question_text']}\n\n"
        f"**Schema**\n```json\n{json.dumps(question['table_schema'], indent=2)}\n```\n"
        "Write your SQL in chat and then use action buttons below."
    )
    actions = [
        cl.Action(name="run_sample", payload={}, label="Run Sample Data"),
        cl.Action(name="run_hidden", payload={}, label="Run Hidden Test Cases"),
        cl.Action(name="hint", payload={}, label="Hint"),
    ]
    await cl.Message(content=content, actions=actions).send()


def build_onboarding_graph():
    graph = StateGraph(dict)

    async def load_user_node(state):
        user_id = state["user_id"]
        store.upsert_user(user_id, {"source": "chainlit"})
        return {"user_id": user_id, "questions": store.get_questions(user_id)}

    async def assessment_node(state):
        user_id = state["user_id"]
        questions = state["questions"]
        if questions:
            return {"generated": False}

        generated = await assessment_agent.generate_initial_assessment({"user_id": user_id}, num_questions=5)
        for q in generated:
            qid = q.get("question_id", str(uuid.uuid4()))
            q["question_id"] = qid
            store.save_question(qid, user_id, q, status="pending")
            for topic in q.get("topic_tags", []):
                store.update_knowledge(user_id, topic, 0.5)
        return {"generated": True}

    async def select_pending_node(state):
        pending = store.get_questions(state["user_id"], status="pending")
        question = pending[0]["question_json"] if pending else None
        return {"pending_question": question}

    graph.add_node("load_user", load_user_node)
    graph.add_node("assessment", assessment_node)
    graph.add_node("select_pending", select_pending_node)
    graph.add_edge(START, "load_user")
    graph.add_edge("load_user", "assessment")
    graph.add_edge("assessment", "select_pending")
    graph.add_edge("select_pending", END)
    return graph.compile()


def build_hidden_eval_graph():
    graph = StateGraph(dict)

    def run_student_node(state):
        user_id = state["user_id"]
        question = state["question"]
        sql = state["sql"]
        student = sandbox.execute_query(user_id, sql, question["table_schema"], question["hidden_test_cases"])
        return {"student": student}

    def run_expected_node(state):
        user_id = state["user_id"]
        question = state["question"]
        expected = sandbox.execute_query(
            user_id,
            question["expected_query"],
            question["table_schema"],
            question["hidden_test_cases"],
        )
        return {"expected": expected}

    def evaluate_node(state):
        student = state["student"]
        expected = state["expected"]
        if student["error"]:
            return {"error": f"Execution error: {student['error']}"}
        if expected["error"]:
            return {"error": f"Internal expected-query error: {expected['error']}"}

        report = sandbox.compare_results(student, expected)
        passed = report["passed"]
        return {"report": report, "passed": passed, "error": None}

    def update_state_node(state):
        if state.get("error"):
            return {}

        user_id = state["user_id"]
        question = state["question"]
        passed = state["passed"]

        analytics_agent.update_after_attempt(user_id, question["topic_tags"], passed)
        quality = 5 if passed else 2
        next_date = scheduler_agent.schedule_next(question["question_id"], quality)
        store.upsert_study_item(user_id, question["question_id"], next_date, completed=1 if passed else 0)

        if passed:
            store.mark_question_status(question["question_id"], "completed")
            store.mark_study_completed(user_id, question["question_id"])

        return {"next_date": next_date}

    graph.add_node("run_student", run_student_node)
    graph.add_node("run_expected", run_expected_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("update_state", update_state_node)
    graph.add_edge(START, "run_student")
    graph.add_edge("run_student", "run_expected")
    graph.add_edge("run_expected", "evaluate")
    graph.add_edge("evaluate", "update_state")
    graph.add_edge("update_state", END)
    return graph.compile()


onboarding_graph = build_onboarding_graph()
hidden_eval_graph = build_hidden_eval_graph()


@cl.on_chat_start
async def start_chat():
    user = cl.user_session.get("user")
    user_id = user.identifier if user else f"guest-{uuid.uuid4().hex[:8]}"
    cl.user_session.set("user_id", user_id)

    state = await onboarding_graph.ainvoke({"user_id": user_id})

    if not state.get("pending_question"):
        await cl.Message(content="No pending questions. Great work!").send()
        await render_analytics(user_id)
        return

    await send_question(state["pending_question"])
    await render_analytics(user_id)


@cl.on_message
async def on_message(message):
    cl.user_session.set("student_sql", message.content)
    await cl.Message(content="SQL saved. Click an action button to run checks.").send()


@cl.action_callback("run_sample")
async def run_sample(_):
    user_id = cl.user_session.get("user_id")
    question = get_current_question()
    sql = cl.user_session.get("student_sql", "")
    if not question or not sql:
        await cl.Message(content="Please submit SQL first.").send()
        return

    try:
        result = sandbox.execute_query(user_id, sql, question["table_schema"], question["sample_data"])
        if result["error"]:
            await cl.Message(content=f"Execution error: {result['error']}").send()
            return
        await cl.Message(content=f"Sample result\n```json\n{json.dumps(result, default=str, indent=2)}\n```").send()
    except SQLSandboxError as exc:
        await cl.Message(content=str(exc)).send()


@cl.action_callback("run_hidden")
async def run_hidden(_):
    user_id = cl.user_session.get("user_id")
    question = get_current_question()
    sql = cl.user_session.get("student_sql", "")
    if not question or not sql:
        await cl.Message(content="Please submit SQL first.").send()
        return

    try:
        result = hidden_eval_graph.invoke({"user_id": user_id, "question": question, "sql": sql})

        if result.get("error"):
            await cl.Message(content=result["error"]).send()
            return

        if result["passed"]:
            await cl.Message(content="✅ Hidden tests passed!").send()
        else:
            await cl.Message(content=f"❌ Hidden tests failed.\n```json\n{result['report']['diff']}\n```").send()

        await render_analytics(user_id)

        pending = store.get_questions(user_id, status="pending")
        if pending:
            await send_question(pending[0]["question_json"])
        else:
            weak = sorted(store.get_knowledge_map(user_id), key=lambda x: x["confidence_score"])
            if weak and weak[0]["confidence_score"] < 0.7:
                new_q = await scheduler_agent.generate_question_for_topic(weak[0]["topic"])
                store.save_question(new_q["question_id"], user_id, new_q, status="pending")
                await cl.Message(content="Generated a new practice item for your weak topic.").send()
                await send_question(new_q)
            else:
                await cl.Message(content="You're caught up. Come back on your next scheduled date.").send()
    except SQLSandboxError as exc:
        await cl.Message(content=str(exc)).send()


@cl.action_callback("hint")
async def hint(_):
    question = get_current_question()
    sql = cl.user_session.get("student_sql", "")
    if not question:
        await cl.Message(content="No active question.").send()
        return
    hint_text = await feedback_agent.generate_hint(question, sql)
    await cl.Message(content=f"💡 Hint:\n{hint_text}").send()

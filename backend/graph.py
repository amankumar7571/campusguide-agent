"""LangGraph supervisor graph.

Supervisor routes each question to exactly one specialist agent:
  - sql_agent     — placement-statistics questions
  - writer_agent  — requests to draft a notice / announcement
  - retriever_agent — everything else (handbook / notices / rules RAG)

Conversation memory: LangGraph SqliteSaver checkpointer (SQLite locally;
Postgres checkpointer documented for deployment in README).
Per-request step cap enforced by the graph recursion limit.
"""
import re
from typing import TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from .config import BASE_DIR, MAX_STEPS_PER_REQUEST
from .guardrails import OUT_OF_CORPUS_REPLY, is_on_topic, mask_pii

SQL_HINTS = ["placement stat", "how many offers", "ctc", "salary",
             "which companies", "offers", "recruit", "placed", "package"]
DRAFT_HINTS = ["draft", "write a notice", "write an announcement",
               "prepare a notice", "compose a notice"]


class AgentState(TypedDict, total=False):
    question: str
    route: str
    passages: list
    sql_result: dict
    draft: str
    answer: str
    citations: list
    steps: int


def _route(state: AgentState) -> str:
    q = state["question"].lower()
    if any(h in q for h in DRAFT_HINTS):
        return "writer_agent"
    if any(h in q for h in SQL_HINTS):
        return "sql_agent"
    return "retriever_agent"


def _supervisor(state: AgentState) -> AgentState:
    state["steps"] = state.get("steps", 0) + 1
    state["route"] = _route(state)
    return state


def _answer_from_passages(question: str, passages: list) -> tuple[str, list]:
    """Deterministic extractive answer: only text present in passages."""
    if not passages:
        return OUT_OF_CORPUS_REPLY, []
    citations = sorted({p["citation"] for p in passages})
    lines = []
    for p in passages[:5]:
        snippet = " ".join(p["text"].split())[:400]
        lines.append(f"- {snippet} [{p['citation']}]")
    answer = ("Based on the college documents:\n\n" + "\n".join(lines)
              + "\n\nSources: " + "; ".join(citations))
    return answer, citations


def make_graph(retriever, sql_runner):
    """Build the graph. retriever: Retriever; sql_runner: fn(sql)->(cols,rows)."""
    graph = StateGraph(AgentState)

    def retriever_agent(state: AgentState) -> AgentState:
        state["steps"] = state.get("steps", 0) + 1
        # Off-topic questions get an explicit "I don't know" even if the
        # retriever returns weak, coincidental matches.
        if not is_on_topic(state["question"]):
            state["answer"], state["citations"] = OUT_OF_CORPUS_REPLY, []
            state["passages"] = []
            return state
        passages = retriever.search(state["question"])
        if not passages:
            state["answer"], state["citations"] = OUT_OF_CORPUS_REPLY, []
            state["passages"] = []
            return state
        answer, citations = _answer_from_passages(state["question"], passages)
        state["passages"] = passages
        state["answer"] = mask_pii(answer)
        state["citations"] = citations
        return state

    def sql_agent_node(state: AgentState) -> AgentState:
        state["steps"] = state.get("steps", 0) + 1
        from .sql_agent import natural_language_to_sql
        sql = natural_language_to_sql(state["question"])
        try:
            cols, rows = sql_runner(sql)
        except Exception as exc:  # validation errors surface safely
            state["answer"] = f"Could not run that placement query: {exc}"
            state["citations"] = []
            return state
        state["sql_result"] = {"sql": sql, "columns": cols, "rows": rows}
        if not rows:
            state["answer"] = ("I don't know — no placement records match "
                               "that question in the sample placement data.")
        else:
            parts = [f"{r.get('company', '')} — {r.get('role', '')}: "
                     f"{r.get('offers', r.get('total_offers', ''))} offers"
                     + (f", {r.get('ctc_lpa')} LPA"
                        if r.get("ctc_lpa") else "")
                     for r in rows[:10]]
            state["answer"] = ("From the sample placement records:\n\n- "
                               + "\n- ".join(parts)
                               + "\n\nSource: placement_stats table "
                                 "(sample data).")
        state["citations"] = ["placement_stats table (sample data)"]
        return state

    def writer_agent(state: AgentState) -> AgentState:
        state["steps"] = state.get("steps", 0) + 1
        passages = retriever.search(state["question"])
        if not passages:
            state["answer"] = OUT_OF_CORPUS_REPLY
            state["citations"] = []
            return state
        citations = sorted({p["citation"] for p in passages})
        facts = "\n".join("- " + " ".join(p["text"].split())[:250]
                          for p in passages[:5])
        state["draft"] = (
            "DRAFT NOTICE (pending human approval — not published)\n\n"
            f"Subject: {state['question']}\n\n"
            "Based only on the college documents:\n" + facts
            + "\n\nSources: " + "; ".join(citations))
        state["answer"] = (state["draft"]
                           + "\n\nThis draft is saved as pending approval. "
                             "An admin must approve it before it is published.")
        state["passages"] = passages
        state["citations"] = citations
        return state

    graph.add_node("supervisor", _supervisor)
    graph.add_node("retriever_agent", retriever_agent)
    graph.add_node("sql_agent", sql_agent_node)
    graph.add_node("writer_agent", writer_agent)
    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        lambda s: s["route"],
        {"retriever_agent": "retriever_agent",
         "sql_agent": "sql_agent",
         "writer_agent": "writer_agent"})
    for node in ("retriever_agent", "sql_agent", "writer_agent"):
        graph.add_edge(node, END)

    import sqlite3
    conn = sqlite3.connect(str(BASE_DIR / "checkpoints.sqlite"),
                           check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=[])


def ask(graph, question: str, thread_id: str = "default") -> dict:
    """Run one question through the graph with the step cap as recursion limit."""
    result = graph.invoke(
        {"question": question, "steps": 0},
        config={"configurable": {"thread_id": thread_id},
                "recursion_limit": MAX_STEPS_PER_REQUEST * 2})
    return {
        "answer": result.get("answer", ""),
        "citations": result.get("citations", []),
        "route": result.get("route", ""),
        "passages": result.get("passages", []),
        "sql_result": result.get("sql_result"),
        "draft": result.get("draft"),
    }

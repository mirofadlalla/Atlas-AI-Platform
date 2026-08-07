from langgraph.graph import StateGraph, END

from app.agent.core.state import AgentState
from app.agent.nodes import (
    decompose_node,
    finish_node,
    retrieval_node,
    sql_node,
    thought_node,
    memory_read_node,
    memory_write_node,
    semantic_recall_node,
)
from app.agent.core.router import route_action, route_after_finish

builder = StateGraph(AgentState)

builder.add_node("decompose", decompose_node)
builder.add_node("memory_read", memory_read_node)
builder.add_node("semantic_recall", semantic_recall_node)
builder.add_node("memory_write", memory_write_node)
builder.add_node("think", thought_node)
builder.add_node("sql_tool", sql_node)
builder.add_node("retrieval_tool", retrieval_node)
builder.add_node("finish", finish_node)

builder.set_entry_point("memory_read")
builder.add_edge("memory_read", "semantic_recall")
builder.add_edge("semantic_recall", "decompose")
builder.add_edge("decompose", "think")

builder.add_conditional_edges(
    "think",
    route_action,
    {
        "sql": "sql_tool",
        "retrieval": "retrieval_tool",
        "finish": "finish",
    },
)

builder.add_edge("sql_tool", "think")
builder.add_edge("retrieval_tool", "think")

builder.add_conditional_edges(
    "finish",
    route_after_finish,
    {
        "think": "think",
        "end": "memory_write",
    },
)
builder.add_edge("memory_write", END)

agent_app = builder.compile()

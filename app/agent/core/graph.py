from langgraph.graph import END, StateGraph

from app.agent.core.router import (
    evaluate_tool_sufficiency,
    fast_hybrid_router,
    route_action,
    route_after_finish,
    route_target_path,
)
from app.agent.core.state import AgentState
from app.agent.nodes import (
    decompose_node,
    direct_answer_node,
    finish_node,
    memory_write_node,
    retrieval_node,
    sql_node,
    thought_node,
)

builder = StateGraph(AgentState)

builder.add_node("fast_router", fast_hybrid_router)
builder.add_node("direct_answer", direct_answer_node)
builder.add_node("sql_tool", sql_node)
builder.add_node("retrieval_tool", retrieval_node)
builder.add_node("decompose", decompose_node)
builder.add_node("think", thought_node)
builder.add_node("finish", finish_node)
builder.add_node("memory_write", memory_write_node)

builder.set_entry_point("fast_router")

# Router branch: maps classified intent directly to target node
builder.add_conditional_edges(
    "fast_router",
    route_target_path,
    {
        "direct_answer": "direct_answer",
        "sql_tool": "sql_tool",
        "retrieval_tool": "retrieval_tool",
        "decompose": "decompose",
    },
)

# Direct answer path -> memory write
builder.add_edge("direct_answer", "memory_write")

# Single-pass tool sufficiency check: SUFFICIENT -> finish, INSUFFICIENT -> think
builder.add_conditional_edges(
    "sql_tool",
    evaluate_tool_sufficiency,
    {
        "SUFFICIENT": "finish",
        "INSUFFICIENT": "think",
    },
)

builder.add_conditional_edges(
    "retrieval_tool",
    evaluate_tool_sufficiency,
    {
        "SUFFICIENT": "finish",
        "INSUFFICIENT": "think",
    },
)

# Complex / Agentic planning path
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

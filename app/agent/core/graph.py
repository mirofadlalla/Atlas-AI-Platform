from langgraph.graph import StateGraph, END
from app.agent.core.state import AgentState
from app.agent.nodes.decompose_node import decompose_node
from app.agent.nodes.thought_node import thought_node
from app.agent.nodes.sql_node import sql_node
from app.agent.nodes.retrieval_node import retrieval_node
from app.agent.nodes.finish_node import finish_node
from app.agent.core.router import route_action, route_after_finish

builder = StateGraph(AgentState)

# Add all nodes
builder.add_node("decompose", decompose_node)
builder.add_node("think", thought_node)
builder.add_node("sql_tool", sql_node)
builder.add_node("retrieval_tool", retrieval_node)
builder.add_node("finish", finish_node)

# User Question
#    ↓
# Decompose
#    ↓
# Think (LLM reasoning)
#    ↓
# Router
#    ↓
# (SQL أو Retrieval أو Finish)
#    ↓
# Loop 🔁
#    ↓
# Final Answer

# Set entry point
builder.set_entry_point("decompose")

# Add edge from decompose to think
builder.add_edge("decompose", "think")

# Add conditional edges from think node based on router decision
builder.add_conditional_edges(
    "think",
    route_action,
    {
        "sql": "sql_tool",
        "retrieval": "retrieval_tool",
        "finish": "finish"
    }
)

# Add edges back to think node for continuing the reasoning loop (ReAct loop)
builder.add_edge("sql_tool", "think")
builder.add_edge("retrieval_tool", "think")

# Add conditional edge after finish node to handle sub-questions
builder.add_conditional_edges(
    "finish",
    route_after_finish,
    {
        "think": "think",
        "end": END
    }
)

# Compile the graph
agent_app = builder.compile()
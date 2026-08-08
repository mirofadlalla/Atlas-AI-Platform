from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field


class ActionDecision(BaseModel):
    """Decision model for the agent's next action."""

    thought: str = Field(
        description="Reasoning about the current situation and what to do next"
    )
    action: str = Field(
        description="The action to take: 'sql', 'retrieval', or 'finish'"
    )

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "thought": "The user is asking for data analysis, I should use SQL to query the database",
                    "action": "sql",
                },
                {
                    "thought": "I need more context about the topic, let me retrieve relevant documents",
                    "action": "retrieval",
                },
                {
                    "thought": "I have gathered enough information to answer the question",
                    "action": "finish",
                },
            ]
        }


format_instructions = JsonOutputParser(
    pydantic_object=ActionDecision
).get_format_instructions()

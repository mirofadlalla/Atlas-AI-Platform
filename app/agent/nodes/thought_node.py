from app.agent.schemas import ActionDecision, format_instructions
from app.services.llm_runner import call_llama
from app.agent.core.state import AgentState
import re


def extract_first_json_block(text: str) -> str:
    text = text.strip()

    code_block_pattern = r'```(?:json)?\s*([\s\S]*?)```'
    code_blocks = re.findall(code_block_pattern, text)

    if code_blocks:
        text = code_blocks[0].strip()

    brace_count = 0
    first_json = []
    in_string = False
    escape_next = False

    for i, char in enumerate(text):
        if escape_next:
            first_json.append(char)
            escape_next = False
            continue

        if char == '\\' and in_string:
            escape_next = True
            first_json.append(char)
            continue

        if char == '"' and not escape_next:
            in_string = not in_string

        first_json.append(char)

        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    return ''.join(first_json).strip()

    return ''.join(first_json).strip()


def thought_node(state: AgentState):
    """
    ONLY responsible for reasoning + selecting next action.
    NO safety logic here.
    """

    has_sql = bool(state.get('last_sql'))
    has_retrieval = bool(state.get('retrieval_context'))

    actions = []
    if has_sql:
        actions.append("SQL already executed")
    if has_retrieval:
        actions.append("Retrieval already executed")

    actions_context = "\n".join(actions) if actions else "None"

    sub_questions = state.get('sub_questions', [state.get('question', '')])
    idx = state.get('current_sub_question_index', 0)
    current_question = sub_questions[idx] if idx < len(sub_questions) else state.get('question', '')

    question_type = _classify_question_type(current_question)

    if question_type == "data":
        guidance = "Use SQL"
    elif question_type == "knowledge":
        guidance = "Use RETRIEVAL"
    else:
        guidance = "Decide best action"

    prompt = f"""
You are an AI agent.

Question: {current_question}
Step: {state.get("step_count", 0)}

Previous actions:
{actions_context}

Guidance: {guidance}

Return ONLY JSON:
{format_instructions}
"""

    response = call_llama(prompt)
    response_text = response["content"]

    next_action = _parse_action_decision(response_text)

    return {
        **state,
        "thought": response_text,
        "last_action": next_action,
        "step_count": state.get("step_count", 0) + 1,
        "observation_history": state.get("observation_history", []) + [
            f"Decision = {next_action}"
        ]
    }


def _parse_action_decision(response_text: str) -> str:
    try:
        json_text = extract_first_json_block(response_text)
        action_decision = ActionDecision.model_validate_json(json_text)
        action = action_decision.action.lower().strip()

        if action in ["sql", "retrieval", "finish"]:
            return action

    except Exception as e:
        print(f"[PARSE ERROR] {e}")

    return "finish"


def _classify_question_type(question: str) -> str:
    q = question.lower()

    data_patterns = [
        'how many', 'count', 'total', 'sum', 'average',
        'number of', 'revenue', 'sales', 'statistics'
    ]

    knowledge_patterns = [
        'what is', 'explain', 'describe', 'how does',
        'why', 'definition', 'information'
    ]

    data_score = sum(p in q for p in data_patterns)
    knowledge_score = sum(p in q for p in knowledge_patterns)

    if data_score > knowledge_score:
        return "data"
    elif knowledge_score > data_score:
        return "knowledge"

    return "knowledge"
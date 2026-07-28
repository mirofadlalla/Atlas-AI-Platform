def route_action(state):
    """
    THE ONLY place for control logic.
    Prevent loops, enforce execution rules.
    """

    last_action = state.get("last_action", "finish")

    has_sql_data = bool(state.get("sql_result") or state.get("last_sql"))
    has_sql_results = state.get("sql_has_results", False)
    has_retrieval_data = bool(state.get("retrieval_context"))

    sql_attempted = state.get("sql_attempted", False)
    retrieval_attempted = state.get("retrieval_attempted", False)

    observation_history = state.get("observation_history", [])
    step_count = state.get("step_count", 0)

    from app.agent.nodes.thought_node import _classify_question_type
    question_type = _classify_question_type(state.get("question", ""))

    # 1. Hard stop
    if step_count >= 6:
        print("[ROUTER] Max steps reached → FINISH")
        return "finish"

    # 2. Validate action
    if last_action not in ["sql", "retrieval", "finish"]:
        return "finish"

    # 3. Loop detection
    if len(observation_history) >= 2:
        if observation_history[-1] == observation_history[-2]:
            print("[ROUTER] Repeated decision → FINISH")
            return "finish"

    # 4. Success → finish
    if last_action == "sql" and has_sql_results:
        return "finish"

    if last_action == "retrieval" and has_retrieval_data:
        return "finish"

    # 5. SQL failed → try retrieval
    if last_action == "sql" and sql_attempted and not has_sql_data:
        if not retrieval_attempted:
            print("[ROUTER] SQL failed → trying retrieval")
            return "retrieval"
        return "finish"

    # 6. Retrieval failed → finish
    if last_action == "retrieval" and retrieval_attempted and not has_retrieval_data:
        return "finish"

    # 7. Force data if needed
    if last_action == "finish":
        if question_type == "data" and not has_sql_data:
            print("[ROUTER] Forcing SQL")
            return "sql"

        if question_type == "knowledge" and not has_retrieval_data:
            print("[ROUTER] Forcing retrieval")
            return "retrieval"

    return last_action


def route_after_finish(state):
    """
    Move to next sub-question or end.
    """

    idx = state.get("current_sub_question_index", 0)
    subs = state.get("sub_questions", [])

    if idx < len(subs):
        print(f"[ROUTER] Next sub-question {idx+1}/{len(subs)}")
        return "think"
    else:
        print("[ROUTER] All done")
        return "end"
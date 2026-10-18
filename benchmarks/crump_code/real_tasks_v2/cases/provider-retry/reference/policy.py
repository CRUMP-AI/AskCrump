def retryable(task, code):
    return not task.get("provider_started") and task["attempt"] < task["maximum"] and code in {"timeout","network"}

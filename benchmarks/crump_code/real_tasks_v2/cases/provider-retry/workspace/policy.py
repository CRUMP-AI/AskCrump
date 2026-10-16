def retryable(task, code):
    return task["attempt"] < task["maximum"] and code in {"timeout","network"}

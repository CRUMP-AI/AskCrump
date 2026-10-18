def verdict(workspace,required):
    return "completed" if workspace.checks and all(c["code"]==0 for c in workspace.checks) else "failed"

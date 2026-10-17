def verdict(workspace,required):
    if workspace.generation==0: return "completed"
    if not required: return "failed"
    latest={}
    for check in workspace.checks:
        if check["generation"]==workspace.generation: latest[check["command"]]=check["code"]
    return "completed" if all(name in latest and type(latest[name]) is int and latest[name]==0 for name in required) else "failed"

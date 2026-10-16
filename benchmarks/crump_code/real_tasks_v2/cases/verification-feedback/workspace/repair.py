async def run(workspace,propose,max_turns):
    for turn in range(max_turns):
        claim=await propose(None)
        if claim.get("success"): return "completed"
        receipt=await workspace.verify()
        if receipt.get("returnCode")==0: return "completed"
    return "failed"

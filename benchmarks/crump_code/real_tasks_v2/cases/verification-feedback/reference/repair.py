async def run(workspace,propose,max_turns):
    if type(max_turns) is not int or max_turns<1: raise ValueError("turn budget")
    feedback=None
    for turn in range(max_turns):
        await propose(feedback)
        receipt=await workspace.verify()
        if isinstance(receipt,dict) and type(receipt.get("returnCode")) is int and receipt["returnCode"]==0 and receipt.get("revision")==workspace.revision:
            return "completed"
        feedback=receipt
    return "failed"

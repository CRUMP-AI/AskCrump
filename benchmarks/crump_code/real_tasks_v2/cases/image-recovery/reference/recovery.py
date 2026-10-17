def sanitize(item):
    result={"role":item["role"],"content":item.get("content","")}
    expected={"IMAGE_SAFETY_REJECTED":"prompt_or_reference","INVALID_IMAGE_EDIT_SOURCE":"reference","IMAGE_EDIT_SOURCE_TOO_LARGE":"reference"}
    code=item.get("replyErrorCode")
    if item["role"]=="user" and code in expected:
        result["replyErrorCode"]=code; r=item.get("replyRecovery")
        if isinstance(r,dict) and r.get("action")=="revise_image_request" and r.get("usageRestored") is True and r.get("changeRequired",expected[code])==expected[code]:
            result["replyRecovery"]={"action":"revise_image_request","usageRestored":True,"changeRequired":expected[code]}
    return result

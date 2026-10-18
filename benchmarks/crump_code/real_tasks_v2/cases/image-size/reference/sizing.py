import math
def prepare(width,height,max_edge,max_pixels,encoded_bytes,max_bytes):
    if any(type(v) is not int or v<=0 for v in (width,height,max_edge,max_pixels,max_bytes)) or type(encoded_bytes) is not int or encoded_bytes<0 or encoded_bytes>=max_bytes: raise ValueError("image bounds")
    scale=min(1,max_edge/max(width,height),math.sqrt(max_pixels/(width*height)))
    w=max(1,math.floor(width*scale)); h=max(1,math.floor(height*scale))
    if w*h>max_pixels or max(w,h)>max_edge: raise ValueError("unrepresentable bounds")
    return w,h

def prepare(width,height,max_edge,max_pixels,encoded_bytes,max_bytes):
    scale=min(1,max_edge/max(width,height))
    return round(width*scale),round(height*scale)

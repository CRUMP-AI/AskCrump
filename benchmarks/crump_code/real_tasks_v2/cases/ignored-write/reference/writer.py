from pathlib import PurePosixPath
async def write(fs, git, path, content):
    status=await git.check_ignore(path)
    if status==0: raise ValueError("ignored")
    if status!=1: raise RuntimeError("eligibility unknown")
    parent=str(PurePosixPath(path).parent)
    if parent!=".": await fs.mkdir(parent)
    await fs.write(path,content)
    return path

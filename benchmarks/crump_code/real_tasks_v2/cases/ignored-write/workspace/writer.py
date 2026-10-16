async def write(fs, git, path, content):
    await fs.write(path,content)
    if await git.check_ignore(path)==0: raise ValueError("ignored")
    return path

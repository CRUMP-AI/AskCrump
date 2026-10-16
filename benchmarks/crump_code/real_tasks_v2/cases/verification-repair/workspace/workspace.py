class Workspace:
    def __init__(self): self.generation=0; self.checks=[]
    def edit(self): self.generation+=1
    def check(self,command,code): self.checks.append({"command":command,"code":code,"generation":0})

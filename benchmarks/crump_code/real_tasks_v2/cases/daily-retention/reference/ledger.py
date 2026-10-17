class Ledger:
    def __init__(self): self.rows={}; self.days={}
    def totals(self,day): return self.days.get(day,(0,None))
    def reserve(self,id,day,amount,cap):
        if id in self.rows or type(amount) is not int or amount<=0 or type(cap) is not int or cap<=0: raise ValueError("admission")
        used,oldcap=self.totals(day); effective=min(cap,oldcap) if oldcap is not None else cap
        if used+amount>effective: raise ValueError("budget")
        self.rows[id]={"day":day,"reserved":amount,"held":amount,"cap":cap}
        self.days[day]=(used+amount,effective)
    def _hold(self,id,value):
        if id not in self.rows or type(value) is not int or value<0: raise ValueError("settlement")
        row=self.rows[id]; used,cap=self.days[row["day"]]
        self.days[row["day"]]=(used+value-row["held"],cap); row["held"]=value
    def settle(self,id,actual,uncertain=False):
        if id not in self.rows or type(actual) is not int or actual<0: raise ValueError("settlement")
        self._hold(id,max(self.rows[id]["reserved"],actual) if uncertain else actual)
    def release(self,id): self._hold(id,0)
    def erase(self,id): self.rows.pop(id)

class Ledger:
    def __init__(self): self.rows={}
    def totals(self,day):
        rows=[r for r in self.rows.values() if r["day"]==day]
        return sum(r["held"] for r in rows),min((r["cap"] for r in rows),default=None)
    def reserve(self,id,day,amount,cap):
        used,oldcap=self.totals(day)
        if used+amount>cap: raise ValueError("budget")
        self.rows[id]={"day":day,"reserved":amount,"held":amount,"cap":cap}
    def settle(self,id,actual,uncertain=False): self.rows[id]["held"]=actual
    def release(self,id): self.rows[id]["held"]=0
    def erase(self,id): self.rows.pop(id)

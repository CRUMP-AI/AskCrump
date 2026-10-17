class Boot:
    def __init__(self,armed,install,enter,register):
        self.armed=armed; self.install=install; self.enter=enter; self.register=register; self.entered=False; self.registered=False
        if armed: install()
    def _enter(self):
        if self.armed and not self.entered: self.entered=True; self.enter()
    def shell_ready(self): self._enter()
    def dom_ready(self):
        self._enter()
        if self.armed and not self.registered: self.registered=True; self.register()

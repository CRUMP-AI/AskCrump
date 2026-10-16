class Boot:
    def __init__(self,armed,install,enter,register):
        self.armed=armed; self.install=install; self.enter=enter; self.register=register
        if armed: enter()
    def shell_ready(self):
        if self.armed: self.install(); self.enter()
    def dom_ready(self):
        if self.armed: self.enter(); self.register()

class Inventory:
    def __init__(self, stock):
        self.stock = stock

    def available(self, quantity):
        return quantity <= self.stock

    def reserve(self, quantity):
        if not self.available(quantity):
            raise ValueError("insufficient stock")
        self.stock -= quantity
        return self.stock

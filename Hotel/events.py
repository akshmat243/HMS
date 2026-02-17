from MBP.events import BaseEvent

class BookingCreatedEvent(BaseEvent):
    def __init__(self, booking):
        self.booking = booking

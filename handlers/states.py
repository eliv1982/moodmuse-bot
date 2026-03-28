"""
FSM states for greeting card creation flow.
"""
from aiogram.fsm.state import State, StatesGroup


class CardStates(StatesGroup):
    """Steps of the greeting card creation."""

    choosing_language = State()
    choosing_occasion = State()
    image_description = State()
    holiday = State()
    image_style = State()
    text_style = State()
    generating = State()

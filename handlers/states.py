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
    occasion_details_toggle = State()
    occasion_details = State()
    image_style = State()
    text_style = State()
    recipient_address_toggle = State()
    recipient_address = State()
    signature_toggle = State()
    sender_signature = State()
    generating = State()


class CreationStates(StatesGroup):
    """Guided creation: both modes ("choose from options", "my idea") fill one creative brief."""

    choosing_mode = State()
    concept = State()
    mood = State()
    style = State()
    inscription = State()
    preferences = State()
    caption = State()
    idea = State()
    clarifying = State()
    awaiting_text = State()
    reviewing_suggestion = State()
    confirming = State()
    generating = State()


class ProfileStates(StatesGroup):
    """Profile onboarding and name editing."""

    onboarding_name = State()
    confirming_name = State()
    editing_name = State()

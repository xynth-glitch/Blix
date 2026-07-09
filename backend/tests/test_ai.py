from blix.ai import _fallback_answer
from blix.models.assistant import AssistantContext


def test_fallback_refuses_off_topic():
    answer = _fallback_answer("write me a poem", AssistantContext())
    assert "Delhi bus" in answer
    assert "routes" in answer


def test_fallback_asks_for_grounding_when_no_context():
    answer = _fallback_answer("where is my bus?", AssistantContext())
    assert "bus number" in answer
    assert "current location" in answer

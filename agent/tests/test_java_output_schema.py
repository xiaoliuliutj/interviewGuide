import pytest

from agent.LLM.jsonSchemaValidator import OutputSchemaValidationError, parseJsonObject, validateOutput


SCHEMA = {
    "type": "object",
    "required": ["score", "priority"],
    "additionalProperties": False,
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "priority": {"type": "string", "enum": ["HIGH", "LOW"]},
    },
}


def testJavaSchemaAcceptsFencedJsonObject() -> None:
    payload = parseJsonObject("```json\n{\"score\": 80, \"priority\": \"HIGH\"}\n```")
    validateOutput(payload, SCHEMA)


def testJavaSchemaRejectsBusinessShapeMismatch() -> None:
    with pytest.raises(OutputSchemaValidationError):
        validateOutput({"score": "80", "priority": "HIGH"}, SCHEMA)

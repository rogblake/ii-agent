"""Regression tests for ii_agent.agent.runtime.models.vertexai.claude."""

from ii_agent.agent.runtime.models.vertexai.claude import Claude
from ii_agent.core.logger import logger


class TestVertexAIClaudeDebugLogging:
    def test_get_request_params_with_debug_sink_does_not_raise(self):
        model = Claude(max_tokens=1234, temperature=0.1)

        sink_id = logger.add(lambda _: None, level="DEBUG")
        try:
            params = model.get_request_params()
        finally:
            logger.remove(sink_id)

        assert params["max_tokens"] == 1234
        assert params["temperature"] == 0.1

    def test_prepare_request_kwargs_with_debug_sink_does_not_raise(self):
        model = Claude(max_tokens=1234)

        sink_id = logger.add(lambda _: None, level="DEBUG")
        try:
            kwargs = model._prepare_request_kwargs("System prompt")
        finally:
            logger.remove(sink_id)

        assert kwargs["max_tokens"] == 1234
        assert kwargs["system"][0]["text"] == "System prompt"

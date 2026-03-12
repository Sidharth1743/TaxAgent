import os
from dotenv import load_dotenv

load_dotenv()

from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask

# Check new context aggregators structure
try:
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
        LLMUserAggregatorParams,
    )
    from pipecat.processors.aggregators.llm_context import LLMContext
    print("universal aggregators ok")
except ImportError:
    pass

from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService, GeminiLiveLLMSettings

try:
    from pipecat.transports.network.fastapi_websocket import FastAPIWebsocketTransport, FastAPIWebsocketParams
    print("fastapi websocket transport standard ok")
except ImportError:
    try:
        from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
        print("fastapi websocket transport alternative ok")
    except ImportError:
        print("failed to import FastAPIWebsocketTransport")

from pipecat.audio.vad.silero import SileroVADAnalyzer
try:
    from pipecat.audio.vad.vad_analyzer import VADParams
except ImportError:
   pass

print("OK")

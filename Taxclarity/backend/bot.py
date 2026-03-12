import os
import sys

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from loguru import logger

# Add the project root to sys.path so 'backend' can be resolved
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=True)

import base64  # noqa: E402
import json  # noqa: E402

from pipecat.adapters.schemas.function_schema import FunctionSchema  # noqa: E402
from pipecat.adapters.schemas.tools_schema import ToolsSchema  # noqa: E402
from pipecat.audio.vad.silero import SileroVADAnalyzer  # noqa: E402
from pipecat.audio.vad.vad_analyzer import VADParams  # noqa: E402
from pipecat.frames.frames import (  # noqa: E402
    Frame,
    InputAudioRawFrame,
    InputImageRawFrame,
    LLMRunFrame,
    OutputAudioRawFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.runner import PipelineRunner  # noqa: E402
from pipecat.pipeline.task import PipelineParams, PipelineTask  # noqa: E402
from pipecat.processors.aggregators.llm_context import LLMContext  # noqa: E402
from pipecat.processors.aggregators.llm_response_universal import (  # noqa: E402
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.serializers.base_serializer import FrameSerializer  # noqa: E402
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService  # noqa: E402
from pipecat.services.llm_service import FunctionCallParams  # noqa: E402
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport  # noqa: E402

app = FastAPI()

# System instruction for the Gemini Live agent
SYSTEM_INSTRUCTION = """
You are a highly helpful and professional Tax Advisor Assistant.
You specialize in USA and Indian taxes, as well as cross-border scenarios.
Always be polite, concise, and friendly.

If the user asks a complex tax question or about specific jurisdictions, YOU MUST use the `ask_geo_router` tool to get the accurate answer.
Pass a concise summary of their query to the tool.
When the tool returns a response, summarize the advice clearly for the user in a conversational tone. Do not expose internal routing details like "jurisdiction: india", just provide the helpful advice.
"""

class BotFrameSerializer(FrameSerializer):
    def __init__(self):
        super().__init__()

    async def serialize(self, frame: Frame) -> str | bytes | None:
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio # return raw PCM bytes for the frontend to play directly
        if isinstance(frame, TextFrame):
            return json.dumps({"type": "text", "text": frame.text})
        if isinstance(frame, TranscriptionFrame):
            return json.dumps({
                "type": "transcription",
                "text": frame.text,
                "user_id": frame.user_id,
                "timestamp": frame.timestamp
            })
        return None

    async def deserialize(self, data: str | bytes) -> Frame | None:
        if isinstance(data, bytes):
            # Binary data is raw PCM audio from microphone (16kHz, 1 channel, 16-bit)
            return InputAudioRawFrame(audio=data, sample_rate=16000, num_channels=1)
        if isinstance(data, str):
            try:
                msg = json.loads(data)
                if msg.get("type") == "video":
                    b64_data = msg.get("data")
                    # handle data URIs
                    if "base64," in b64_data:
                        b64_data = b64_data.split("base64,")[1]
                    image_bytes = base64.b64decode(b64_data)
                    return InputImageRawFrame(image=image_bytes, format="JPEG", size=(0, 0))
            except Exception as e:
                logger.error(f"Error deserializing text frame: {e}")
        return None

async def ask_geo_router(params: FunctionCallParams):
    """Tool handler for the geo router"""
    logger.info(f"Tool call invoked: ask_geo_router with args: {params.arguments}")

    query = params.arguments.get("query", "")

    # We dynamically import this so we reuse the existing geo_router integration
    try:
        from backend.websocket_server import process_voice_query
        result = await process_voice_query(query)
        logger.info(f"Tool call result: {result}")
        await params.result_callback(result)
    except Exception as e:
        logger.error(f"Error in ask_geo_router: {e}")
        await params.result_callback({"error": str(e), "message": "Failed to look up tax advice."})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("New WebSocket connection accepted.")

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_out_enabled=True,
            add_wav_header=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5)),
            vad_audio_passthrough=True,
            serializer=BotFrameSerializer()
        )
    )

    # Note: Using pure pipecat-ai[google] (non-Vertex) with API Key
    geo_router_schema = FunctionSchema(
        name="ask_geo_router",
        description="Ask the tax geo router agent for specific advice regarding US, Indian, or cross-border tax issues.",
        properties={
            "query": {
                "type": "string",
                "description": "The concise tax query to be routed for professional advice.",
            }
        },
        required=["query"],
    )

    tools = ToolsSchema(standard_tools=[geo_router_schema])

    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        tools=tools
    )

    llm.register_function("ask_geo_router", ask_geo_router)

    context = LLMContext([
        {"role": "system", "content": SYSTEM_INSTRUCTION},
        {"role": "user", "content": "Say hello to the user and ask how you can help them with their taxes today."}
    ])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.5))
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            llm,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        )
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected to transport")
        # Kick off the conversation.
        await task.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected from transport")
        await task.cancel()

    runner = PipelineRunner()

    try:
        await runner.run(task)
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
    finally:
        logger.info("WebSocket session ended.")


if __name__ == "__main__":
    logger.info("Starting Pipecat Bot Server on port 8003...")
    uvicorn.run("backend.bot:app", host="0.0.0.0", port=8003, log_level="info", reload=True)

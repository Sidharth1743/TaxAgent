import asyncio
import base64
import os
import inspect
from dotenv import load_dotenv
from google import genai
import traceback

load_dotenv()

async def main():
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    config = {
        "generation_config": {
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {
                        "voice_name": "Aoede",
                    }
                }
            }
        }
    }
    
    session_cm = client.aio.live.connect(model="gemini-2.5-flash-native-audio-latest", config=config)
    session = await session_cm.__aenter__()

    try:
        print("Trying to send text...")
        await session.send_realtime_input(text="Hello")
        print("Sent text successfully via kwarg")
    except Exception as e:
        print(f"ERROR text positional: {type(e).__name__}: {e}")
        
    finally:
        await session_cm.__aexit__(None, None, None)

if __name__ == "__main__":
    asyncio.run(main())

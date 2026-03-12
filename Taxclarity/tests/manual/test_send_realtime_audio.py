import asyncio
import base64
import os
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
    try:
        async with client.aio.live.connect(model="gemini-2.5-flash-native-audio-latest", config=config) as session:
            try:
                print("Trying to send audio...")
                audio_data = b'00000000'
                b64_audio = base64.b64encode(audio_data).decode("utf-8")
                await session.send_realtime_input(audio={"mime_type": "audio/pcm", "data": b64_audio})
                print("Sent successfully")
            except Exception as e:
                print(f"ERROR: {type(e).__name__}: {e}")
                traceback.print_exc()
    except Exception as e:
            print(f"Outer ERROR: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(main())

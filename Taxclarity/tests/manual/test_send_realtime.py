import asyncio
import os
import inspect
from dotenv import load_dotenv
from google import genai

load_dotenv()

async def main():
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    async with client.aio.live.connect(model="gemini-2.0-flash-exp") as session:
        try:
            print("Trying to send dummy audio...")
            await session.send_realtime_input(audio={"mime_type": "audio/pcm", "data": "abcd"})
            print("Sent successfully")
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(main())

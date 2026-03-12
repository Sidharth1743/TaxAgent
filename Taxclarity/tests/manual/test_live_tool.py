import asyncio
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

async def main():
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    try:
        async with client.aio.live.connect(
            model="gemini-2.5-flash-native-audio-latest",
            config={
                "system_instruction": {"parts": [{"text": "You are a tax assistant."}]},
                "generation_config": {
                    "response_modalities": ["AUDIO"],
                }
            }
        ) as session:
            print("Successfully connected!")
            await session.send(input="Hello?")
            async for response in session.receive():
                print(response)
                break
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

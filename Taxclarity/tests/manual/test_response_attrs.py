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
                print(dir(response))
                if getattr(response, "server_content", None):
                    print("HAS SERVER CONTENT")
                    turn = response.server_content.model_turn
                    if turn:
                        print("HAS MODEL TURN")
                        for part in turn.parts:
                            print(dir(part))
                            if getattr(part, "text", None):
                                print("TEXT:", part.text)
                            if getattr(part, "inline_data", None):
                                print("AUDIO DATA LEN:", len(part.inline_data.data))
                break
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

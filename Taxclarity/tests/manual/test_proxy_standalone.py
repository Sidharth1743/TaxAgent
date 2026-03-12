import asyncio
import base64
from backend.websocket_server import GeminiLiveProxy

async def main():
    proxy = GeminiLiveProxy()
    print("Connecting object...")
    await proxy.connect(session_id="test_id")
    print("Connected.")
    
    try:
        audio_data = b'00000000'
        await proxy.send_audio(audio_data)
        print("Sent successfully through proxy object!")
    except Exception as e:
        import traceback
        print(f"ERROR proxy positional: {type(e).__name__}: {e}")
        traceback.print_exc()
        
    finally:
        await proxy.close()

if __name__ == "__main__":
    asyncio.run(main())

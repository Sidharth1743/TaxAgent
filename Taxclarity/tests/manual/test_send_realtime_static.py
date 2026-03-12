import inspect
from google.genai.live import AsyncSession

print("Signature for AsyncSession.send_realtime_input:")
print(inspect.signature(AsyncSession.send_realtime_input))

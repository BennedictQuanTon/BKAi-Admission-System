import asyncio
import edge_tts

async def main():
    try:
        comm = edge_tts.Communicate("Xin chào", "vi-VN-HoaiMyNeural", rate="+0%", volume="+0%")
        await comm.save("test.mp3")
        print("Success")
    except Exception as e:
        print(f"Error: {repr(e)}")

asyncio.run(main())

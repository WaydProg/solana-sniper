import asyncio, json, websockets   # pip install websockets

async def main():
    async with websockets.connect("wss://pumpdev.io/ws") as ws:
        await ws.send(json.dumps({"method": "subscribeNewToken"}))
        async for raw in ws:
            event = json.loads(raw)
            if event.get("txType") == "create":
                print(event["name"], event["symbol"], f'https://pump.fun/coin/{event["mint"]}')

asyncio.run(main())
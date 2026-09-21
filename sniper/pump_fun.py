import json
import websockets
import asyncio
import logging

async def listen_pump_fun(callback):
    url = "wss://pumpdev.io/ws"
    
    # Внешний цикл для автоматического переподключения при разрыве связи
    while True:
        try:
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({"method": "subscribeNewToken"}))
                logging.info("Успешно подключились к вебсокету Pump Fun")
                
                async for raw in ws:
                    event = json.loads(raw)
                    if event.get("txType") == "create":
                        # Передаем токен в функцию обработки вместо return
                        await callback(event)
                        
        except Exception as e:
            logging.error(f"Ошибка сокета: {e}. Переподключение через 5 секунд...")
            await asyncio.sleep(5)
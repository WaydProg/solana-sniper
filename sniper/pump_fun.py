import json
import asyncio
import logging
from collections.abc import Awaitable, Callable

import websockets


class PumpStream:
    """
    Одно вебсокет-соединение с Pump.fun: поток новых токенов и подписки на сделки по отдельным токенам.
    Чтение сокета никогда не ждет обработчиков — иначе при всплеске запусков события копятся в буфере.
    """

    def __init__(self, url: str, on_create: Callable[[dict], None]):
        self.url = url
        self.on_create = on_create
        self.trade_handlers: dict[str, Callable[[dict], None]] = {}
        self.ws = None
        self.connected = asyncio.Event()

    async def _send(self, payload: dict):
        if self.ws is None:
            return
        try:
            await self.ws.send(json.dumps(payload))
        except websockets.ConnectionClosed:
            # Подписки восстановятся после переподключения
            pass

    async def watch(self, mint: str, handler: Callable[[dict], None]):
        self.trade_handlers[mint] = handler
        await self._send({"method": "subscribeTokenTrade", "keys": [mint]})

    async def unwatch(self, mint: str):
        if self.trade_handlers.pop(mint, None) is not None:
            await self._send({"method": "unsubscribeTokenTrade", "keys": [mint]})

    def _dispatch(self, event: dict):
        tx_type = event.get("txType")
        if tx_type == "create":
            self.on_create(event)
        elif tx_type in ("buy", "sell"):
            handler = self.trade_handlers.get(event.get("mint"))
            if handler:
                handler(event)

    async def run(self):
        # Внешний цикл для автоматического переподключения при разрыве связи
        while True:
            try:
                async with websockets.connect(self.url, ping_interval=20, max_queue=None) as ws:
                    self.ws = ws
                    await ws.send(json.dumps({"method": "subscribeNewToken"}))
                    if self.trade_handlers:
                        await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": list(self.trade_handlers)}))
                    self.connected.set()
                    logging.info("Успешно подключились к вебсокету Pump Fun")

                    async for raw in ws:
                        try:
                            self._dispatch(json.loads(raw))
                        except Exception:
                            logging.exception("Ошибка обработки события вебсокета")

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.error(f"Ошибка сокета: {e}. Переподключение через 5 секунд...")
            finally:
                self.ws = None
                self.connected.clear()
            await asyncio.sleep(5)

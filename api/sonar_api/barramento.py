"""Barramento em memória que entrega eventos aos clientes SSE.

Os eventos podem nascer em outra thread (cliente MQTT, threadpool do FastAPI);
cada inscrito guarda o seu event loop e recebe por call_soon_threadsafe.
"""

import asyncio
import threading
from collections import defaultdict


class Barramento:
    def __init__(self) -> None:
        self._inscritos: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = defaultdict(set)
        self._trava = threading.Lock()

    def inscrever(self, canal: str) -> asyncio.Queue:
        fila: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._trava:
            self._inscritos[canal].add((asyncio.get_running_loop(), fila))
        return fila

    def cancelar(self, canal: str, fila: asyncio.Queue) -> None:
        with self._trava:
            self._inscritos[canal] = {item for item in self._inscritos[canal] if item[1] is not fila}
            if not self._inscritos[canal]:
                del self._inscritos[canal]

    def publicar(self, canal: str, evento: dict) -> None:
        with self._trava:
            alvos = list(self._inscritos.get(canal, ()))
        for loop, fila in alvos:
            try:
                loop.call_soon_threadsafe(self._entregar, fila, evento)
            except RuntimeError:  # loop já encerrado
                self.cancelar(canal, fila)

    @staticmethod
    def _entregar(fila: asyncio.Queue, evento: dict) -> None:
        try:
            fila.put_nowait(evento)
        except asyncio.QueueFull:
            pass  # cliente lento: ele recupera o que perdeu pelo Last-Event-ID

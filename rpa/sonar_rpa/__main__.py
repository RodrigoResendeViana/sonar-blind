import argparse
import os
import time

import httpx

from .robo import processar


def main() -> None:
    p = argparse.ArgumentParser(prog="sonar_rpa")
    p.add_argument("--uma-vez", action="store_true", help="roda uma vez e sai")
    p.add_argument("--real", action="store_true", help="registra de verdade (padrão: simulado)")
    p.add_argument("--intervalo", type=int, default=900)
    a = p.parse_args()
    cliente = httpx.Client(
        base_url=os.environ["SONAR_API_URL"],
        headers={"Authorization": f"Bearer {os.environ['SONAR_TOKEN']}"},
        timeout=30,
    )
    while True:
        print(processar(cliente, simular=not a.real), flush=True)
        if a.uma_vez:
            break
        time.sleep(a.intervalo)


if __name__ == "__main__":
    main()

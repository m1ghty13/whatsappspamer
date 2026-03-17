"""
Xivora — управление лицензиями
"""

import urllib.request
import urllib.error
import json

SERVER = "https://licenseserver111-xivora.waw0.amvera.tech"
API_KEY = "LmhZCGw5"

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
}


def request(method, path, body=None):
    url = SERVER + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())


def show_menu():
    print("\n" + "─" * 40)
    print("  Xivora — License Manager")
    print("─" * 40)
    print("  1. Показать все коды")
    print("  2. Добавить код")
    print("  3. Отозвать код")
    print("  4. Сбросить устройство (reset HWID)")
    print("  0. Выход")
    print("─" * 40)


def cmd_list():
    data = request("GET", "/license/list")
    if not data:
        print("  Список пуст.")
        return
    print(f"\n  {'КОД':<20} {'СТАТУС':<10} {'УСТРОЙСТВО'}")
    print("  " + "─" * 60)
    for r in data:
        hwid = r["hwid"][:16] + "…" if r["hwid"] else "(не привязан)"
        status = r["status"]
        marker = "✓" if status == "active" else "✗"
        print(f"  {marker} {r['code']:<20} {status:<10} {hwid}")


def cmd_add():
    code = input("\n  Введите код: ").strip()
    if not code:
        print("  Отменено.")
        return
    result = request("POST", "/license/add", {"code": code})
    if result.get("ok"):
        print(f"  ✓ Код добавлен: {code}")
    else:
        print(f"  ✗ Ошибка: {result}")


def cmd_revoke():
    code = input("\n  Введите код для отзыва: ").strip()
    if not code:
        print("  Отменено.")
        return
    confirm = input(f"  Отозвать «{code}»? (y/n): ").strip().lower()
    if confirm != "y":
        print("  Отменено.")
        return
    result = request("POST", "/license/revoke", {"code": code})
    if result.get("ok"):
        print(f"  ✓ Код отозван: {code}")
    else:
        print(f"  ✗ Ошибка: {result}")


def cmd_reset():
    code = input("\n  Введите код для сброса устройства: ").strip()
    if not code:
        print("  Отменено.")
        return
    result = request("POST", "/license/reset", {"code": code})
    if result.get("ok"):
        print(f"  ✓ Устройство сброшено. Код можно активировать на новом ПК: {code}")
    else:
        print(f"  ✗ Ошибка: {result}")


COMMANDS = {
    "1": cmd_list,
    "2": cmd_add,
    "3": cmd_revoke,
    "4": cmd_reset,
}

if __name__ == "__main__":
    while True:
        show_menu()
        choice = input("  Выбор: ").strip()
        if choice == "0":
            break
        elif choice in COMMANDS:
            COMMANDS[choice]()
        else:
            print("  Неверный выбор.")

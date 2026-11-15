"""Notification-area icon of the linked agent (Bloque 4, authorized 15/11/2026; optional dependency pystray).

The icon shows whether the agent is linked and to whom, opens ContaSuite or the agent's log, and stops the agent.
It never shows codes, tokens or folder paths. Without pystray the agent runs exactly as before, without an icon.
"""

import logging
import os
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ICON_FILES = [
    ROOT / 'frontend/dist/icons/original/claro/64/CS_ContaSuite.png',
    ROOT / 'frontend/public/icons/original/claro/64/CS_ContaSuite.png',
]
# Status dot: linked (green), waiting for a sign-in (gray).
COLORS = {True: (22, 163, 74, 255), False: (148, 163, 184, 255)}


def available():
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def base_image():
    from PIL import Image, ImageDraw

    for path in ICON_FILES:
        if path.is_file():
            return Image.open(path).convert('RGBA').resize((64, 64))
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 62, 62), radius=14, fill=(37, 99, 235, 255))
    draw.text((17, 22), 'CS', fill=(255, 255, 255, 255))
    return image


def with_dot(image, linked):
    from PIL import ImageDraw

    image = image.copy()
    draw = ImageDraw.Draw(image)
    draw.ellipse((40, 40, 62, 62), fill=COLORS[linked], outline=(255, 255, 255, 255), width=3)
    return image


def tooltip(status):
    text = 'ContaSuite · ' + ('Agente vinculado como ' + status['user'] if status['paired'] else status['notice'])
    return text[:120]  # Windows limits the tooltip length


def run(agent, app_url, log_file=None, stop_event=None):
    """Blocks on the main thread with the icon; the agent itself works in background threads."""
    import pystray

    stop_event = stop_event or threading.Event()
    base = base_image()
    images = {linked: with_dot(base, linked) for linked in (True, False)}

    def status_text(_item):
        status = agent.status()
        return 'Vinculado como ' + status['user'] if status['paired'] else 'Sin vincular: inicia sesión en ContaSuite'

    def open_app(_icon, _item):
        webbrowser.open(app_url)

    def open_log(_icon, _item):
        if log_file and Path(log_file).is_file():
            os.startfile(log_file)  # noqa: S606 - the user's own log file, opened with its associated app

    def stop(icon, _item):
        stop_event.set()
        icon.stop()

    icon = pystray.Icon(
        'ContaSuite agente',
        images[False],
        'ContaSuite · Agente local',
        menu=pystray.Menu(
            pystray.MenuItem(status_text, None, enabled=False),
            pystray.MenuItem('Abrir ContaSuite', open_app, default=True),
            pystray.MenuItem('Abrir registro del agente', open_log, enabled=lambda _item: bool(log_file)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('Detener el agente', stop),
        ),
    )

    def refresh():
        last = None
        while not stop_event.wait(2):
            status = agent.status()
            current = (status['paired'], status['user'], status['notice'])
            if current != last:
                icon.icon = images[status['paired']]
                icon.title = tooltip(status)
                icon.update_menu()
                last = current
        icon.stop()

    def setup(icon):
        icon.visible = True
        threading.Thread(target=refresh, daemon=True).start()

    logging.info('Icono del agente en el área de notificación.')
    icon.run(setup=setup)
    stop_event.set()

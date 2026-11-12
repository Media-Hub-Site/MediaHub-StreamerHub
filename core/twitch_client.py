"""
core/twitch_client.py
─────────────────────
Conector en tiempo real para Twitch IRC y Eventos de Canal (EventSub / Tags IRC).
Permite conectarse a cualquier canal de Twitch en modo lectura instantáneo (justinfan)
o autenticado con OAuth para capturar mensajes del chat, Bits/Cheers, Suscripciones,
Raids y canjes de Puntos del Canal (custom-reward-id) en directo.
"""

import socket
import threading
import random
import time
from PyQt6.QtCore import QObject, pyqtSignal


class TwitchIRCBridge(QObject):
    chat_received = pyqtSignal(str, str)                  # (username, message)
    event_received = pyqtSignal(str, str, str, int, str)  # (type, username, message, amount, badge)
    status_changed = pyqtSignal(bool, str)                # (connected, status_text)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sock: socket.socket | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self.channel = ""

    def connect_channel(self, channel: str, oauth_token: str = ""):
        self.disconnect_channel()
        clean_channel = channel.strip().lower().lstrip("#")
        if not clean_channel:
            self.status_changed.emit(False, "Canal vacío")
            return

        self.channel = clean_channel
        self._running = True
        self._thread = threading.Thread(
            target=self._irc_loop,
            args=(clean_channel, oauth_token.strip()),
            daemon=True,
        )
        self._thread.start()

    def disconnect_channel(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self.status_changed.emit(False, "Desconectado")

    def _irc_loop(self, channel: str, oauth_token: str):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(15.0)
            sock.connect(("irc.chat.twitch.tv", 6667))
            self._sock = sock

            # Solicitar tags y comandos de Twitch para detectar Subs, Raids, Bits y Puntos de Canal
            sock.sendall(b"CAP REQ :twitch.tv/tags twitch.tv/commands\r\n")

            if oauth_token:
                tok = oauth_token if oauth_token.startswith("oauth:") else f"oauth:{oauth_token}"
                sock.sendall(f"PASS {tok}\r\n".encode("utf-8"))
                sock.sendall(f"NICK {channel}\r\n".encode("utf-8"))
            else:
                anon_nick = f"justinfan{random.randint(10000, 99999)}"
                sock.sendall(b"PASS SCHMOOPIIE\r\n")
                sock.sendall(f"NICK {anon_nick}\r\n".encode("utf-8"))

            sock.sendall(f"JOIN #{channel}\r\n".encode("utf-8"))
            self.status_changed.emit(True, f"Conectado en vivo a #{channel}")

            sock.settimeout(1.0)
            buffer = ""
            while self._running:
                try:
                    chunk = sock.recv(4096).decode("utf-8", errors="ignore")
                    if not chunk:
                        break
                    buffer += chunk
                    while "\r\n" in buffer:
                        line, buffer = buffer.split("\r\n", 1)
                        self._handle_irc_line(line)
                except socket.timeout:
                    continue
                except Exception:
                    break
        except Exception as e:
            self.status_changed.emit(False, f"Error de conexión: {e}")
        finally:
            self._running = False
            self.status_changed.emit(False, "Desconectado")

    def _parse_tags(self, raw_tags: str) -> dict:
        tags = {}
        for item in raw_tags.lstrip("@").split(";"):
            if "=" in item:
                k, v = item.split("=", 1)
                tags[k] = v
        return tags

    def _handle_irc_line(self, line: str):
        if line.startswith("PING"):
            if self._sock:
                try:
                    self._sock.sendall(b"PONG :tmi.twitch.tv\r\n")
                except Exception:
                    pass
            return

        tags = {}
        rest = line
        if rest.startswith("@"):
            parts = rest.split(" ", 1)
            tags = self._parse_tags(parts[0])
            rest = parts[1] if len(parts) > 1 else ""

        display_name = tags.get("display-name") or "TwitchUser"

        # USERNOTICE: Suscripciones, Resubs, Subgifts, Raids
        if " USERNOTICE " in rest:
            msg_id = tags.get("msg-id", "")
            user_msg = ""
            if " :" in rest:
                user_msg = rest.split(" :", 1)[1]
            if msg_id in ("sub", "resub", "subgift", "anonsubgift"):
                self.event_received.emit(
                    "sub",
                    display_name,
                    user_msg or "¡Se ha suscrito al canal en directo!",
                    1,
                    "NUEVO SUSCRIPTOR • TWITCH",
                )
            elif msg_id == "raid":
                raiders = int(tags.get("msg-param-viewerCount", "10") or 10)
                self.event_received.emit(
                    "raid",
                    display_name,
                    f"¡Raid entrante con {raiders} espectadores!",
                    raiders,
                    f"RAID EN VIVO • {raiders} VIEWERS",
                )
            return

        # PRIVMSG: Mensajes del chat, Bits y Canjes de Puntos del Canal
        if " PRIVMSG " in rest:
            if " :" not in rest:
                return
            prefix, text = rest.split(" :", 1)
            if display_name == "TwitchUser" and "!" in prefix:
                display_name = prefix.split("!", 1)[0].lstrip(":")

            self.chat_received.emit(display_name, text)

            # Detectar Bits / Cheers
            if "bits" in tags and str(tags["bits"]).isdigit():
                bits_amt = int(tags["bits"])
                self.event_received.emit(
                    "bits",
                    display_name,
                    text,
                    bits_amt,
                    f"CHEER • {bits_amt} BITS",
                )
            # Detectar Canje de Puntos del Canal con texto (custom-reward-id)
            elif "custom-reward-id" in tags:
                self.event_received.emit(
                    "channel_points",
                    display_name,
                    text,
                    500,
                    "PUNTOS DEL CANAL • VOZ IA",
                )

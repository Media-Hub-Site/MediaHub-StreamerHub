"""
core/twitch_client.py
─────────────────────
Integración real con Twitch para MediaHub-StreamStudio:
1. TwitchHelixClient:
   - Validación OAuth 2.0 real contra https://id.twitch.tv/oauth2/validate (autodescubre client_id, user_id, login y scopes).
   - Consultas reales a Twitch Helix API (/helix/users, /helix/channels, /helix/streams, /helix/channels/followers, /helix/streams/key).
   - Actualización real de Título del Stream y Categoría/Juego (PATCH /helix/channels + /helix/search/categories).
   - Importación y sincronización directa de Clave de Transmisión (Stream Key) con perfiles locales de OBS Studio (%APPDATA%/obs-studio).
2. TwitchIRCBridge:
   - Conexión bidireccional al chat de Twitch (lectura y escritura de mensajes reales en el stream, comandos !tts y !metas,
     detección de Bits, Suscripciones, Raids y Puntos del Canal).
"""

import os
import json
import socket
import threading
import random
from urllib.parse import urlencode, quote
import requests
from PyQt6.QtCore import QObject, pyqtSignal


TWITCH_SCOPES = [
    "chat:read",
    "chat:edit",
    "channel:manage:broadcast",
    "channel:read:redemptions",
    "channel:manage:redemptions",
    "moderator:read:followers",
    "channel:read:subscriptions",
    "bits:read",
    "channel:read:stream_key",
]


def clean_oauth_token(raw: str) -> str:
    t = (raw or "").strip()
    if t.lower().startswith("oauth:"):
        t = t[6:].strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return t


class TwitchHelixClient:
    """Cliente oficial para Twitch OAuth2 + Helix API y sincronización de Stream Key con OBS Studio."""

    @staticmethod
    def build_oauth_url(client_id: str, port: int = 8899) -> str:
        redirect_uri = f"http://localhost:{port}/auth/callback"
        params = {
            "client_id": client_id.strip(),
            "redirect_uri": redirect_uri,
            "response_type": "token",
            "scope": " ".join(TWITCH_SCOPES),
            "force_verify": "true",
        }
        return f"https://id.twitch.tv/oauth2/authorize?{urlencode(params)}"

    @staticmethod
    def validate_token(oauth_token: str) -> dict:
        """
        Valida un token OAuth contra id.twitch.tv/oauth2/validate.
        No requiere conocer el Client-ID de antemano: Twitch devuelve el client_id, login, user_id y scopes.
        """
        tok = clean_oauth_token(oauth_token)
        if not tok:
            return {"valid": False, "error": "Token vacío"}
        try:
            r = requests.get(
                "https://id.twitch.tv/oauth2/validate",
                headers={"Authorization": f"OAuth {tok}"},
                timeout=8,
            )
            if r.status_code == 200:
                data = r.json()
                return {
                    "valid": True,
                    "token": tok,
                    "client_id": data.get("client_id", ""),
                    "login": data.get("login", ""),
                    "user_id": str(data.get("user_id", "")),
                    "scopes": data.get("scopes", []) or [],
                    "expires_in": data.get("expires_in", 0),
                }
            return {"valid": False, "error": f"Token inválido o expirado (HTTP {r.status_code})"}
        except Exception as e:
            return {"valid": False, "error": f"Error de red validando token: {e}"}

    @classmethod
    def fetch_account_snapshot(cls, oauth_token: str, client_id: str = "", channel_hint: str = "") -> dict:
        """
        Obtiene el estado real de la cuenta de Twitch desde Helix API:
        perfil, avatar, título actual del directo, juego/categoría, estado EN VIVO, espectadores,
        total de seguidores y clave de transmisión (si el token tiene el permiso).
        """
        val = cls.validate_token(oauth_token)
        if not val.get("valid"):
            return {"ok": False, "error": val.get("error", "Token inválido")}

        tok = val["token"]
        cid = val.get("client_id") or client_id.strip()
        uid = val.get("user_id", "")
        login = val.get("login") or channel_hint.strip().lower()

        headers = {
            "Authorization": f"Bearer {tok}",
            "Client-Id": cid,
        }

        result = {
            "ok": True,
            "token": tok,
            "client_id": cid,
            "user_id": uid,
            "login": login,
            "display_name": login,
            "profile_image_url": "",
            "avatar_bytes": None,
            "broadcaster_type": "",
            "stream_title": "",
            "stream_game": "",
            "is_live": False,
            "viewer_count": 0,
            "followers_total": None,
            "recent_followers": [],
            "stream_key": "",
            "scopes": val.get("scopes", []),
        }

        try:
            # 1. Datos de usuario (/helix/users)
            u_resp = requests.get("https://api.twitch.tv/helix/users", headers=headers, timeout=8)
            if u_resp.status_code == 200:
                users = u_resp.json().get("data", [])
                if users:
                    u = users[0]
                    uid = str(u.get("id", uid))
                    result["user_id"] = uid
                    result["login"] = u.get("login", login)
                    result["display_name"] = u.get("display_name", result["login"])
                    result["profile_image_url"] = u.get("profile_image_url", "")
                    result["broadcaster_type"] = u.get("broadcaster_type", "")
                    if result["profile_image_url"]:
                        try:
                            img_r = requests.get(result["profile_image_url"], timeout=6)
                            if img_r.status_code == 200:
                                result["avatar_bytes"] = img_r.content
                        except Exception:
                            pass

            if not uid:
                return result

            # 2. Información del canal: Título y Categoría (/helix/channels)
            ch_resp = requests.get(
                f"https://api.twitch.tv/helix/channels?broadcaster_id={uid}",
                headers=headers,
                timeout=8,
            )
            if ch_resp.status_code == 200:
                ch_data = ch_resp.json().get("data", [])
                if ch_data:
                    c = ch_data[0]
                    result["stream_title"] = c.get("title", "")
                    result["stream_game"] = c.get("game_name", "")

            # 3. Estado del stream EN VIVO (/helix/streams)
            st_resp = requests.get(
                f"https://api.twitch.tv/helix/streams?user_id={uid}",
                headers=headers,
                timeout=8,
            )
            if st_resp.status_code == 200:
                st_data = st_resp.json().get("data", [])
                if st_data:
                    s = st_data[0]
                    result["is_live"] = s.get("type") == "live"
                    result["viewer_count"] = int(s.get("viewer_count", 0))
                    if s.get("title"):
                        result["stream_title"] = s["title"]
                    if s.get("game_name"):
                        result["stream_game"] = s["game_name"]

            # 4. Seguidores del canal (/helix/channels/followers)
            fl_resp = requests.get(
                f"https://api.twitch.tv/helix/channels/followers?broadcaster_id={uid}&first=10",
                headers=headers,
                timeout=8,
            )
            if fl_resp.status_code == 200:
                fl_json = fl_resp.json()
                result["followers_total"] = int(fl_json.get("total", 0))
                result["recent_followers"] = [
                    {
                        "user_name": f.get("user_name") or f.get("user_login", ""),
                        "followed_at": f.get("followed_at", ""),
                    }
                    for f in fl_json.get("data", [])
                ]

            # 5. Clave de Transmisión (/helix/streams/key) si el token incluye channel:read:stream_key
            if "channel:read:stream_key" in result["scopes"]:
                sk_resp = requests.get(
                    f"https://api.twitch.tv/helix/streams/key?broadcaster_id={uid}",
                    headers=headers,
                    timeout=8,
                )
                if sk_resp.status_code == 200:
                    sk_data = sk_resp.json().get("data", [])
                    if sk_data:
                        result["stream_key"] = sk_data[0].get("stream_key", "")
        except Exception as e:
            result["warning"] = str(e)

        return result

    @classmethod
    def update_stream_info(
        cls, oauth_token: str, client_id: str, broadcaster_id: str, title: str, game_name: str
    ) -> tuple[bool, str, str]:
        """
        Actualiza realmente el título y la categoría/juego del canal de Twitch vía PATCH /helix/channels.
        Retorna (exito, mensaje, nombre_juego_resuelto).
        """
        tok = clean_oauth_token(oauth_token)
        if not tok:
            return False, "Inicia sesión con tu Token OAuth de Twitch para actualizar el stream.", game_name

        if not client_id or not broadcaster_id:
            val = cls.validate_token(tok)
            if not val.get("valid"):
                return False, val.get("error", "Token inválido"), game_name
            client_id = val.get("client_id", "")
            broadcaster_id = val.get("user_id", "")

        headers = {
            "Authorization": f"Bearer {tok}",
            "Client-Id": client_id,
            "Content-Type": "application/json",
        }

        payload: dict[str, str] = {}
        if title.strip():
            payload["title"] = title.strip()

        resolved_game = game_name.strip()
        if resolved_game:
            try:
                q = quote(resolved_game)
                cat_resp = requests.get(
                    f"https://api.twitch.tv/helix/search/categories?query={q}&first=1",
                    headers=headers,
                    timeout=8,
                )
                if cat_resp.status_code == 200:
                    cats = cat_resp.json().get("data", [])
                    if cats:
                        payload["game_id"] = str(cats[0]["id"])
                        resolved_game = cats[0].get("name", resolved_game)
            except Exception:
                pass

        if not payload:
            return False, "Escribe un título o categoría para actualizar.", resolved_game

        try:
            r = requests.patch(
                f"https://api.twitch.tv/helix/channels?broadcaster_id={broadcaster_id}",
                headers=headers,
                json=payload,
                timeout=8,
            )
            if r.status_code in (200, 204):
                return True, "¡Título y categoría actualizados en tu canal de Twitch!", resolved_game
            if r.status_code == 401 or r.status_code == 403:
                return (
                    False,
                    "Tu token necesita el permiso 'channel:manage:broadcast' para editar el título del directo.",
                    resolved_game,
                )
            return False, f"Twitch respondió HTTP {r.status_code}: {r.text[:120]}", resolved_game
        except Exception as e:
            return False, f"Error de conexión con Twitch Helix: {e}", resolved_game

    @staticmethod
    def import_obs_stream_key() -> tuple[bool, str, str, str]:
        """
        Busca perfiles locales de OBS Studio en %APPDATA%/obs-studio/basic/profiles/*/service.json
        y extrae la Clave de Transmisión (Stream Key) y servidor RTMP si existen.
        Retorna (encontrado, stream_key, server, nombre_perfil).
        """
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return False, "", "", ""
        profiles_dir = os.path.join(appdata, "obs-studio", "basic", "profiles")
        if not os.path.isdir(profiles_dir):
            return False, "", "", ""

        for prof_name in os.listdir(profiles_dir):
            svc_file = os.path.join(profiles_dir, prof_name, "service.json")
            if os.path.isfile(svc_file):
                try:
                    with open(svc_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    settings = data.get("settings", {})
                    key = settings.get("key", "").strip()
                    server = settings.get("server", "rtmp://live.twitch.tv/app/").strip()
                    if key:
                        return True, key, server or "rtmp://live.twitch.tv/app/", prof_name
                except Exception:
                    continue
        return False, "", "", ""

    @staticmethod
    def export_obs_stream_key(stream_key: str, rtmp_server: str = "rtmp://live.twitch.tv/app/") -> tuple[bool, str]:
        """
        Sincroniza la Clave de Transmisión de Twitch directamente en el perfil de OBS Studio del usuario
        (%APPDATA%/obs-studio/basic/profiles/*/service.json).
        """
        key = (stream_key or "").strip()
        if not key:
            return False, "Ingresa primero tu Clave de Transmisión (live_...)"

        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            return False, "No se detectó carpeta APPDATA en el sistema."

        profiles_dir = os.path.join(appdata, "obs-studio", "basic", "profiles")
        os.makedirs(profiles_dir, exist_ok=True)
        existing = [
            d for d in os.listdir(profiles_dir) if os.path.isdir(os.path.join(profiles_dir, d))
        ]
        target_profiles = existing if existing else ["StreamStudio_Twitch"]

        payload = {
            "settings": {
                "bwtest": False,
                "key": key,
                "server": rtmp_server.strip() or "auto",
                "service": "Twitch",
                "use_auth": False,
            },
            "type": "rtmp_common",
        }

        updated = []
        for prof in target_profiles:
            pdir = os.path.join(profiles_dir, prof)
            os.makedirs(pdir, exist_ok=True)
            svc_path = os.path.join(pdir, "service.json")
            try:
                with open(svc_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=4)
                updated.append(prof)
            except Exception:
                continue

        if updated:
            return True, f"Clave sincronizada en OBS Studio (Perfil: {', '.join(updated)})"
        return False, "No se pudo escribir el perfil de OBS Studio."


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
        self.nick = ""
        self.authenticated = False

    def connect_channel(self, channel: str, oauth_token: str = "", bot_login: str = ""):
        self.disconnect_channel()
        clean_channel = channel.strip().lower().lstrip("#")
        if not clean_channel:
            self.status_changed.emit(False, "Canal vacío")
            return

        self.channel = clean_channel
        self._running = True
        self._thread = threading.Thread(
            target=self._irc_loop,
            args=(clean_channel, clean_oauth_token(oauth_token), bot_login.strip().lower()),
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
        self.authenticated = False
        self.status_changed.emit(False, "Desconectado")

    def send_message(self, message: str) -> bool:
        """Envía un mensaje real al chat del canal de Twitch conectado (requiere sesión OAuth)."""
        msg = (message or "").strip()
        if not msg or not self._running or not self._sock or not self.channel:
            return False
        if not self.authenticated:
            return False
        try:
            self._sock.sendall(f"PRIVMSG #{self.channel} :{msg}\r\n".encode("utf-8"))
            self.chat_received.emit(self.nick or self.channel, msg)
            return True
        except Exception:
            return False

    def _irc_loop(self, channel: str, clean_tok: str, bot_login: str):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(15.0)
            sock.connect(("irc.chat.twitch.tv", 6667))
            self._sock = sock

            sock.sendall(b"CAP REQ :twitch.tv/tags twitch.tv/commands twitch.tv/membership\r\n")

            if clean_tok:
                nick = bot_login or channel
                self.nick = nick
                self.authenticated = True
                sock.sendall(f"PASS oauth:{clean_tok}\r\n".encode("utf-8"))
                sock.sendall(f"NICK {nick}\r\n".encode("utf-8"))
            else:
                anon_nick = f"justinfan{random.randint(10000, 99999)}"
                self.nick = anon_nick
                self.authenticated = False
                sock.sendall(b"PASS SCHMOOPIIE\r\n")
                sock.sendall(f"NICK {anon_nick}\r\n".encode("utf-8"))

            sock.sendall(f"JOIN #{channel}\r\n".encode("utf-8"))
            mode_txt = "OAuth lectura/escritura" if self.authenticated else "Modo lectura"
            self.status_changed.emit(True, f"#{channel} ({mode_txt})")

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
            self.authenticated = False
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

        # Detectar fallo de autenticación IRC
        if "NOTICE * :Login authentication failed" in rest or "NOTICE * :Improperly formatted auth" in rest:
            self.status_changed.emit(False, "Token OAuth rechazado por Twitch IRC")
            self._running = False
            return

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

        # PRIVMSG: Mensajes del chat, Bits, Comandos (!tts) y Canjes de Puntos del Canal
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
            # Comando en vivo !tts <mensaje> o !voz <mensaje> en el chat del stream
            elif text.strip().lower().startswith(("!tts ", "!voz ")):
                spoken_msg = text.strip().split(" ", 1)[1].strip()
                if spoken_msg:
                    self.event_received.emit(
                        "channel_points",
                        display_name,
                        f"{display_name} dice: {spoken_msg}",
                        100,
                        "COMANDO CHAT • VOZ IA",
                    )

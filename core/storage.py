"""
core/storage.py
───────────────
Almacenamiento persistente local para MediaHub-StreamStudio (~/.mediahub/streamstudio_data.json).
Guarda configuración de overlays OBS, perfiles de voz IA, recompensas de puntos del canal de Twitch,
lista negra de moderación (SafeStream Guard) e historial de eventos/analíticas.
"""

import os
import json
from datetime import datetime


DEFAULT_DATA = {
    "twitch": {
        "channel": "",
        "oauth_token": "",
        "client_id": "",
        "auto_connect": False,
    },
    "overlay": {
        "port": 8899,
        "theme": "twitch_purple",  # twitch_purple, cyber_cyan, emerald_neon, crimson_fire
        "duration_sec": 6,
        "sound_chime": "crystal",  # crystal, arcade, fanfare, cyber, mute
        "show_goals_in_overlay": True,
        "follower_goal_current": 42,
        "follower_goal_target": 100,
        "sub_goal_current": 8,
        "sub_goal_target": 25,
    },
    "tts": {
        "enabled": True,
        "persona": "narrador_epico",  # narrador_epico, ia_cyber, comentarista_hype, asistente_suave
        "rate": 1,     # -4 a +4
        "volume": 95,  # 0 a 100
        "read_channel_points": True,
        "read_bits": True,
        "read_subs": True,
        "min_bits_for_tts": 10,
        "filter_links": True,
        "banned_words": ["spam", "scam", "hate", "trolllink"],
    },
    "rewards": [
        {
            "id": "tts_highlight",
            "title": "Mensaje con Voz IA en Directo",
            "cost": 500,
            "persona": "narrador_epico",
            "alert_badge": "PUNTOS DEL CANAL • VOZ IA",
            "enabled": True,
        },
        {
            "id": "hype_siren",
            "title": "Alerta de Hype en Pantalla + Saludo IA",
            "cost": 1200,
            "persona": "comentarista_hype",
            "alert_badge": "RECOMPENSA VIP • HYPE",
            "enabled": True,
        },
        {
            "id": "cyber_oracle",
            "title": "Pregunta al Oráculo IA del Stream",
            "cost": 2000,
            "persona": "ia_cyber",
            "alert_badge": "ORÁCULO IA • PUNTOS",
            "enabled": True,
        },
        {
            "id": "hydrate_alert",
            "title": "¡Hora de Hidratarse! (Recordatorio con Voz)",
            "cost": 300,
            "persona": "asistente_suave",
            "alert_badge": "SALUD STREAMER",
            "enabled": True,
        },
    ],
    "events": [],
}


class StorageManager:
    def __init__(self):
        home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        self.base_dir = os.path.join(home, ".mediahub")
        os.makedirs(self.base_dir, exist_ok=True)
        self.file_path = os.path.join(self.base_dir, "streamstudio_data.json")
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.isfile(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                merged = json.loads(json.dumps(DEFAULT_DATA))
                for k, v in loaded.items():
                    if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
                        merged[k].update(v)
                    else:
                        merged[k] = v
                return merged
            except Exception:
                pass
        return json.loads(json.dumps(DEFAULT_DATA))

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando configuración de StreamStudio: {e}")

    def record_event(self, event_type: str, username: str, message: str, amount: int = 0, tts_used: bool = False, badge: str = "") -> dict:
        now_str = datetime.now().strftime("%H:%M:%S")
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        evt = {
            "id": f"evt_{int(datetime.now().timestamp() * 1000)}",
            "time": now_str,
            "timestamp": date_str,
            "type": event_type,  # follow, sub, bits, raid, channel_points
            "username": username,
            "message": message,
            "amount": amount,
            "tts_used": tts_used,
            "badge": badge,
        }
        self.data.setdefault("events", []).insert(0, evt)
        # Mantener últimos 250 eventos
        if len(self.data["events"]) > 250:
            self.data["events"] = self.data["events"][:250]

        # Actualizar metas automáticamente
        ov = self.data.get("overlay", {})
        if event_type == "follow":
            ov["follower_goal_current"] = ov.get("follower_goal_current", 0) + 1
        elif event_type == "sub":
            ov["sub_goal_current"] = ov.get("sub_goal_current", 0) + 1

        self.save()
        return evt

    def get_analytics_summary(self) -> dict:
        events = self.data.get("events", [])
        follows = sum(1 for e in events if e.get("type") == "follow")
        subs = sum(1 for e in events if e.get("type") == "sub")
        bits_total = sum(int(e.get("amount", 0)) for e in events if e.get("type") == "bits")
        raids = sum(1 for e in events if e.get("type") == "raid")
        raiders_total = sum(int(e.get("amount", 0)) for e in events if e.get("type") == "raid")
        points_count = sum(1 for e in events if e.get("type") == "channel_points")
        points_spent = sum(int(e.get("amount", 0)) for e in events if e.get("type") == "channel_points")
        tts_count = sum(1 for e in events if e.get("tts_used"))

        # Top usuarios activos
        user_counts: dict[str, int] = {}
        for e in events:
            u = e.get("username", "Anónimo")
            user_counts[u] = user_counts.get(u, 0) + 1
        top_users = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "total_events": len(events),
            "follows": follows,
            "subs": subs,
            "bits_total": bits_total,
            "raids": raids,
            "raiders_total": raiders_total,
            "points_count": points_count,
            "points_spent": points_spent,
            "tts_count": tts_count,
            "top_users": top_users,
        }

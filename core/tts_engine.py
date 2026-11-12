"""
core/tts_engine.py
──────────────────
Motor de Voces IA y moderación SafeStream Guard para MediaHub-StreamStudio.
Permite sintetizar voz localmente en Windows sin requerir API Keys externas,
aplicando perfiles de entonación (Personas IA) y filtrando palabras prohibidas o enlaces.
"""

import re
import queue
import threading
import subprocess
import os


VOICE_PERSONAS = {
    "narrador_epico": {
        "name_es": "Narrador Épico de Stream",
        "name_en": "Epic Stream Narrator",
        "rate_offset": 0,
        "pitch_hint": "grave",
        "prefix_es": "",
    },
    "comentarista_hype": {
        "name_es": "Comentarista Hype / Caster",
        "name_en": "Hype Caster Voice",
        "rate_offset": 2,
        "pitch_hint": "alta",
        "prefix_es": "¡Atención chat! ",
    },
    "ia_cyber": {
        "name_es": "Oráculo IA Cyberpunk",
        "name_en": "Cyberpunk AI Oracle",
        "rate_offset": 1,
        "pitch_hint": "sintetica",
        "prefix_es": "Sistema IA informa: ",
    },
    "asistente_suave": {
        "name_es": "Asistente de Canal Relajado",
        "name_en": "Chill Channel Assistant",
        "rate_offset": -1,
        "pitch_hint": "suave",
        "prefix_es": "",
    },
}


class TTSEngine:
    def __init__(self, storage):
        self.storage = storage
        self._queue: queue.Queue = queue.Queue()
        self._current_proc: subprocess.Popen | None = None
        self._worker = threading.Thread(target=self._process_queue, daemon=True)
        self._worker.start()

    def sanitize_text(self, text: str) -> tuple[bool, str]:
        """
        Filtra enlaces, spam de caracteres repetidos y palabras en la lista negra (SafeStream Guard).
        Retorna (permitido: bool, texto_limpio: str).
        """
        if not text or not text.strip():
            return False, ""

        clean = text.strip()
        tts_cfg = self.storage.data.get("tts", {})

        # 1. Filtrar URLs si está activado
        if tts_cfg.get("filter_links", True):
            clean = re.sub(r"https?://\S+|www\.\S+", "[enlace bloqueado]", clean, flags=re.IGNORECASE)

        # 2. Filtrar palabras prohibidas
        banned = tts_cfg.get("banned_words", [])
        lower_clean = clean.lower()
        for word in banned:
            w = word.strip().lower()
            if w and w in lower_clean:
                pattern = re.compile(re.escape(w), re.IGNORECASE)
                clean = pattern.sub("***", clean)

        # 3. Reducir repetición excesiva de letras (ej: "holaaaaaaaaaaaa" -> "holaaa")
        clean = re.sub(r"(.)\1{4,}", r"\1\1\1", clean)

        # Limitar longitud máxima para evitar bloqueos de voz
        if len(clean) > 240:
            clean = clean[:240] + "..."

        return True, clean

    def speak(self, text: str, persona_id: str | None = None, force: bool = False) -> str:
        """
        Encola un mensaje para ser leído por el sintetizador de voz IA local
        y retorna el texto sanitizado para el overlay de OBS.
        """
        tts_cfg = self.storage.data.get("tts", {})
        if not force and not tts_cfg.get("enabled", True):
            return ""

        allowed, sanitized = self.sanitize_text(text)
        if not allowed or not sanitized:
            return ""

        chosen_persona = persona_id or tts_cfg.get("persona", "narrador_epico")
        persona_meta = VOICE_PERSONAS.get(chosen_persona, VOICE_PERSONAS["narrador_epico"])

        base_rate = int(tts_cfg.get("rate", 1))
        final_rate = max(-5, min(6, base_rate + int(persona_meta.get("rate_offset", 0))))
        volume = max(0, min(100, int(tts_cfg.get("volume", 95))))

        full_speech = f"{persona_meta.get('prefix_es', '')}{sanitized}"
        self._queue.put((full_speech, final_rate, volume))
        return full_speech

    def stop_current(self):
        """Detiene inmediatamente la locución actual y vacía la cola."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Exception:
                break
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.terminate()
            except Exception:
                pass

    def _process_queue(self):
        while True:
            item = self._queue.get()
            if item is None:
                break
            speech_text, rate, volume = item
            try:
                if os.name == "nt":
                    safe_str = speech_text.replace("'", " ").replace('"', " ").replace("\n", " ").replace("\r", " ")
                    ps_script = (
                        "Add-Type -AssemblyName System.Speech; "
                        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                        f"$s.Rate = {rate}; "
                        f"$s.Volume = {volume}; "
                        f"$s.Speak('{safe_str}');"
                    )
                    creationflags = subprocess.CREATE_NO_WINDOW
                    self._current_proc = subprocess.Popen(
                        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=creationflags,
                    )
                    self._current_proc.wait(timeout=25)
            except Exception:
                pass
            finally:
                self._current_proc = None
                self._queue.task_done()

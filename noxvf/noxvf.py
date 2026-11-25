# NOX VF - doublage français en direct pour NOX REMOTE (fait par math_0235)
# Son du jeu (anglais) -> reconnaissance vocale -> traduction -> voix française,
# avec la voix anglaise baissée en dessous (« voice-over » comme à la télé).
# 100 % gratuit et hors ligne après le premier téléchargement des modèles.

import os
import queue
import socket
import sys
import threading
import time
import tkinter as tk
import json
import tarfile
import zipfile
from tkinter import ttk

import numpy as np

APP = "NOX VF"
HOST, PORT = "127.0.0.1", 47800
BASE = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "NOX VF")
MODELS = os.path.join(BASE, "modeles")
os.makedirs(MODELS, exist_ok=True)

HF = "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR"
VOICES = {
    "femme": ("fr_FR-siwis-medium", f"{HF}/siwis/medium/fr_FR-siwis-medium"),   # PNJ femmes
    "homme": ("fr_FR-tom-medium", f"{HF}/tom/medium/fr_FR-tom-medium"),          # PNJ hommes
    "upmc": ("fr_FR-upmc-medium", f"{HF}/upmc/medium/fr_FR-upmc-medium"),        # Lucia / Jason
    "mls": ("fr_FR-mls-medium", f"{HF}/mls/medium/fr_FR-mls-medium"),            # autres persos de l'histoire
}
SK = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
SPK_URL = f"{SK}/speaker-recongition-models/wespeaker_en_voxceleb_resnet34.onnx"
AT_URL = f"{SK}/audio-tagging-models/sherpa-onnx-ced-mini-audio-tagging-2024-04-19.tar.bz2"
PERSOS_FILE = os.path.join(BASE, "persos.json")
MUSIC_LABELS = {"Music", "Singing", "Song", "Rapping", "Vocal music", "Musical instrument",
                "Pop music", "Hip hop music", "Electronic music", "Rock music", "Techno",
                "Dance music", "Drum", "Bass guitar", "Synthesizer", "Choir"}
SPEECH_LABELS = {"Speech", "Conversation", "Narration, monologue", "Male speech, man speaking",
                 "Female speech, woman speaking", "Shout", "Yell"}
ARGOS_URL = "https://argos-net.com/v1/translate-en_fr-1_9.argosmodel"

# Phrases que Whisper « invente » souvent sur de la musique ou du silence
HALLUCINATIONS = {
    "thank you.", "thanks for watching!", "thank you for watching.", "you", "bye.",
    "thank you so much.", "subscribe", "music", "[music]", "(music)",
}


# ---------------------------------------------------------------- téléchargements
def download(url, dest, status):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    import requests
    tmp = dest + ".part"
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    status(f"Téléchargement {os.path.basename(dest)} : {done * 100 // total} %")
    os.replace(tmp, dest)
    return dest


def get_voice(name, status):
    base, url = VOICES[name]
    onnx = download(url + ".onnx", os.path.join(MODELS, base + ".onnx"), status)
    download(url + ".onnx.json", os.path.join(MODELS, base + ".onnx.json"), status)
    return onnx


def get_tagger_dir(status):
    target = os.path.join(MODELS, "tagging")
    if not os.path.isdir(target):
        z = download(AT_URL, os.path.join(MODELS, "tagging.tar.bz2"), status)
        status("Installation du détecteur de musique...")
        with tarfile.open(z) as tf:
            tf.extractall(target)
    for root, dirs, files in os.walk(target):
        if "model.int8.onnx" in files and "class_labels_indices.csv" in files:
            return root
    raise RuntimeError("Détecteur de musique introuvable")


def get_translator_dir(status):
    target = os.path.join(MODELS, "en_fr")
    if not os.path.isdir(target):
        z = download(ARGOS_URL, os.path.join(MODELS, "en_fr.argosmodel"), status)
        status("Installation du traducteur...")
        with zipfile.ZipFile(z) as zf:
            zf.extractall(target)
    for root, dirs, files in os.walk(target):
        if "sentencepiece.model" in files and "model" in dirs:
            return root
    raise RuntimeError("Modèle de traduction introuvable")


# ---------------------------------------------------------------- moteur IA
class Engine:
    def __init__(self, status):
        self.status = status
        self.whisper = None
        self.translator = None
        self.sp = None
        self.voices = {}
        self.speakers = {}          # nom de voix -> {nom du locuteur: id}
        self.spk = None
        self.tagger = None

    def load(self, whisper_size):
        from faster_whisper import WhisperModel
        import ctranslate2
        import sentencepiece as spm

        status = self.status
        status("Chargement de la reconnaissance vocale (1re fois : téléchargement)...")
        self.whisper = WhisperModel(whisper_size, device="cpu", compute_type="int8",
                                    download_root=os.path.join(MODELS, "whisper"))
        tdir = get_translator_dir(status)
        status("Chargement du traducteur...")
        self.translator = ctranslate2.Translator(os.path.join(tdir, "model"), device="cpu",
                                                 inter_threads=1, intra_threads=2)
        self.sp = spm.SentencePieceProcessor(model_file=os.path.join(tdir, "sentencepiece.model"))
        for name in VOICES:
            onnx = get_voice(name, status)
            self.voices[name] = self._load_voice(onnx)
            try:
                with open(onnx + ".json", encoding="utf-8") as fh:
                    self.speakers[name] = json.load(fh).get("speaker_id_map", {}) or {}
            except (OSError, ValueError):
                self.speakers[name] = {}
        import sherpa_onnx
        status("Chargement de la reconnaissance des personnages...")
        spk = download(SPK_URL, os.path.join(MODELS, "voix_persos.onnx"), status)
        self.spk = sherpa_onnx.SpeakerEmbeddingExtractor(
            sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=spk, num_threads=2))
        tdir2 = get_tagger_dir(status)
        self.tagger = sherpa_onnx.AudioTagging(sherpa_onnx.AudioTaggingConfig(
            model=sherpa_onnx.AudioTaggingModelConfig(ced=os.path.join(tdir2, "model.int8.onnx"), num_threads=2),
            labels=os.path.join(tdir2, "class_labels_indices.csv"), top_k=10))
        status("Prêt")

    def is_music(self, audio16k):
        """True si c'est surtout de la musique / une chanson (radio, voiture...) : on ne double pas."""
        st = self.tagger.create_stream()
        st.accept_waveform(16000, audio16k)
        music = speech = singing = 0.0
        for ev in self.tagger.compute(st):
            if ev.name in MUSIC_LABELS:
                music = max(music, ev.prob)
            if ev.name in ("Singing", "Song", "Rapping", "Vocal music"):
                singing = max(singing, ev.prob)
            if ev.name in SPEECH_LABELS:
                speech = max(speech, ev.prob)
        return singing > 0.25 or (music > 0.35 and music >= speech)

    def embed(self, audio16k):
        st = self.spk.create_stream()
        st.accept_waveform(16000, audio16k)
        st.input_finished()
        e = np.array(self.spk.compute(st), dtype=np.float32)
        return e / (np.linalg.norm(e) + 1e-9)

    @staticmethod
    def _load_voice(onnx):
        from piper import PiperVoice
        return PiperVoice.load(onnx)

    def transcribe(self, audio16k):
        segs, _ = self.whisper.transcribe(audio16k, language="en", beam_size=1,
                                          vad_filter=False, condition_on_previous_text=False,
                                          without_timestamps=True)
        out = []
        for s in segs:
            if s.no_speech_prob > 0.6 or s.avg_logprob < -1.1:
                continue
            t = s.text.strip()
            if not t or "♪" in t or t.lower() in HALLUCINATIONS:
                continue
            out.append(t)
        return " ".join(out).strip()

    def translate(self, text):
        tokens = self.sp.encode(text, out_type=str)
        res = self.translator.translate_batch([tokens], beam_size=2, max_decoding_length=256)
        return self.sp.decode(res[0].hypotheses[0]).replace("▁", " ").strip()

    def speaker_id(self, name, who):
        ids = self.speakers.get(name, {})
        if isinstance(who, int):
            return who if not ids else who % max(1, len(ids))
        if who in ids:
            return ids[who]
        return None

    def speak(self, name, text, speed, who=None):
        """Renvoie (pcm int16 numpy, sample_rate). who = locuteur pour les voix à plusieurs personnes."""
        voice = self.voices[name]
        sid = self.speaker_id(name, who) if who is not None else None
        chunks, rate = [], 22050
        try:  # piper-tts 1.3+
            from piper import SynthesisConfig
            cfg = SynthesisConfig(length_scale=1.0 / speed, speaker_id=sid)
            for c in voice.synthesize(text, syn_config=cfg):
                chunks.append(c.audio_int16_bytes)
                rate = c.sample_rate
        except (ImportError, TypeError, AttributeError):
            rate = voice.config.sample_rate
            kw = {"length_scale": 1.0 / speed}
            if sid is not None:
                kw["speaker_id"] = sid
            for b in voice.synthesize_stream_raw(text, **kw):
                chunks.append(b)
        return np.frombuffer(b"".join(chunks), dtype=np.int16), rate


def pitch_hz(x, rate=16000):
    """Hauteur moyenne de la voix (pour choisir voix d'homme ou de femme)."""
    frame = 1024
    f0s = []
    for i in range(0, len(x) - frame, frame):
        f = x[i:i + frame] - np.mean(x[i:i + frame])
        if np.sqrt(np.mean(f * f)) < 0.01:
            continue
        ac = np.correlate(f, f, mode="full")[frame - 1:]
        lo, hi = rate // 400, rate // 70
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.3 * ac[0]:
            f0s.append(rate / k)
    return float(np.median(f0s)) if f0s else 0.0


# ---------------------------------------------------------------- lecture de l'écran (OCR Windows)
class ScreenReader:
    """Lit les sous-titres français affichés par le jeu dans la fenêtre NOX REMOTE 2 (OCR intégré à Windows, gratuit)."""
    IGNORE = ("Luminosité", "Qualité HD", "VF :", "Capture", "Son ", "NOX REMOTE", "Doublage français")

    def __init__(self):
        import asyncio
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.globalization import Language
        self.loop = asyncio.new_event_loop()
        self.engine = None
        for tag in ("fr-FR", "fr-BE", "fr-CH", "fr-CA"):
            try:
                lang = Language(tag)
                if OcrEngine.is_language_supported(lang):
                    self.engine = OcrEngine.try_create_from_language(lang)
                    break
            except Exception:  # noqa: BLE001
                pass
        if self.engine is None:
            self.engine = OcrEngine.try_create_from_user_profile_languages()
        if self.engine is None:
            raise RuntimeError("Lecture d'écran Windows indisponible (ajoute la langue Français dans Windows)")
        import mss
        self.sct = mss.mss()

    @staticmethod
    def find_window():
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, "NOX REMOTE 2")
        if not hwnd or user32.IsIconic(hwnd):
            return None
        rect = wintypes.RECT()
        pt = wintypes.POINT(0, 0)
        user32.GetClientRect(hwnd, ctypes.byref(rect))
        user32.ClientToScreen(hwnd, ctypes.byref(pt))
        w, h = rect.right - rect.left, rect.bottom - rect.top
        if w < 200 or h < 150:
            return None
        return pt.x, pt.y, w, h

    def _ocr(self, bgra, w, h):
        from winrt.windows.graphics.imaging import SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode
        from winrt.windows.storage.streams import DataWriter
        dw = DataWriter()
        dw.write_bytes(bytes(bgra))
        bmp = SoftwareBitmap.create_copy_from_buffer(dw.detach_buffer(), BitmapPixelFormat.BGRA8, w, h,
                                                     BitmapAlphaMode.PREMULTIPLIED)
        res = self.loop.run_until_complete(self.engine.recognize_async(bmp))
        return [ln.text for ln in res.lines]

    def read_subtitles(self):
        """Texte du bas de l'image (zone des sous-titres)."""
        win = self.find_window()
        if not win:
            return ""
        x, y, w, h = win
        box = {"left": x + int(w * 0.10), "top": y + int(h * 0.70), "width": int(w * 0.80), "height": int(h * 0.24)}
        shot = self.sct.grab(box)
        lines = self._ocr(shot.bgra, shot.width, shot.height)
        lines = [ln.strip() for ln in lines if len(ln.strip()) > 1 and not any(k in ln for k in self.IGNORE)]
        return " ".join(lines).strip()

    def read_screen_names(self, names):
        """Cherche un nom de personnage connu affiché à l'écran (appel, message...)."""
        win = self.find_window()
        if not win:
            return None
        x, y, w, h = win
        shot = self.sct.grab({"left": x, "top": y, "width": w, "height": int(h * 0.70)})
        text = " ".join(self._ocr(shot.bgra, shot.width, shot.height))
        for n in names:
            if n and n in text:
                return n
        return None


def same_text(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() > 0.85


# ---------------------------------------------------------------- personnages
class Persos:
    """Personnages de l'histoire reconnus à leur voix : chacun garde sa propre voix française."""
    DEFAULTS = {"Lucia": ["upmc", "jessica"], "Jason": ["upmc", "pierre"]}

    def __init__(self):
        self.data = {}
        try:
            with open(PERSOS_FILE, encoding="utf-8") as fh:
                self.data = json.load(fh)
        except (OSError, ValueError):
            self.data = {}
        for name, voice in self.DEFAULTS.items():
            self.data.setdefault(name, {"emb": None, "n": 0, "voice": voice})

    def save(self):
        with open(PERSOS_FILE, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh)

    def add_sample(self, name, emb, gender="homme"):
        p = self.data.get(name)
        if p is None:
            # nouveau perso : une voix « mls » différente pour chacun
            used = [v for v in self.data.values() if v["voice"][0] == "mls"]
            idx = 3 + 7 * len(used) + (0 if gender == "homme" else 3)
            p = self.data[name] = {"emb": None, "n": 0, "voice": ["mls", idx]}
        n = p["n"]
        old = np.array(p["emb"], dtype=np.float32) if p["emb"] is not None else np.zeros_like(emb)
        new = (old * n + emb) / (n + 1)
        new /= (np.linalg.norm(new) + 1e-9)
        p["emb"], p["n"] = new.tolist(), n + 1
        self.save()

    def match(self, emb, threshold=0.55):
        best, best_sim = None, threshold
        for name, p in self.data.items():
            if name.startswith("_") or p["emb"] is None:
                continue
            sim = float(np.dot(emb, np.array(p["emb"], dtype=np.float32)))
            if sim > best_sim:
                best, best_sim = name, sim
        return best

    # --- apprentissage automatique : les voix qui reviennent souvent = personnages de l'histoire
    def auto_learn(self, emb, gender, promote_after=6, join=0.6):
        """Regroupe les voix inconnues. Une voix entendue souvent devient un personnage avec sa propre voix.
        La voix d'homme la plus fréquente devient Jason, la voix de femme la plus fréquente devient Lucia."""
        pend = self.data.setdefault("_attente", [])
        best, best_sim = None, join
        for c in pend:
            sim = float(np.dot(emb, np.array(c["emb"], dtype=np.float32)))
            if sim > best_sim:
                best, best_sim = c, sim
        if best is None:
            pend.append({"emb": emb.tolist(), "n": 1, "g": {"homme": 0, "femme": 0}})
            best = pend[-1]
        else:
            n = best["n"]
            new = (np.array(best["emb"], dtype=np.float32) * n + emb) / (n + 1)
            best["emb"], best["n"] = (new / (np.linalg.norm(new) + 1e-9)).tolist(), n + 1
        best["g"][gender] = best["g"].get(gender, 0) + 1
        if len(pend) > 40:                                   # on oublie les voix entendues une seule fois
            pend.sort(key=lambda c: -c["n"])
            del pend[30:]
        if best["n"] >= promote_after:
            g = "femme" if best["g"].get("femme", 0) > best["g"].get("homme", 0) else "homme"
            main = "Lucia" if g == "femme" else "Jason"
            if self.data[main]["emb"] is None:
                name = main
            else:
                k = 1 + sum(1 for v in self.data.values() if isinstance(v, dict) and v.get("auto"))
                name = f"Perso {k}"
            pend.remove(best)
            if name not in self.data:
                used = [v for k2, v in self.data.items() if not k2.startswith("_") and v["voice"][0] == "mls"]
                idx = 3 + 7 * len(used) + (0 if g == "homme" else 3)
                self.data[name] = {"emb": None, "n": 0, "voice": ["mls", idx], "auto": True}
            self.data[name]["emb"], self.data[name]["n"] = best["emb"], best["n"]
            self.save()
            return name
        return None

    def reset(self):
        self.data = {}
        for name, voice in self.DEFAULTS.items():
            self.data[name] = {"emb": None, "n": 0, "voice": voice}
        self.save()


# ---------------------------------------------------------------- application
class NoxVF:
    def __init__(self, root):
        self.root = root
        self.running = False
        self.sock = None
        self.engine = None
        self.seg_q = queue.Queue(maxsize=6)
        self.say_q = queue.Queue(maxsize=6)
        self.ui_q = queue.Queue()
        self.subs = None
        self.persos = Persos()
        self.last_emb = None
        self.last_gender = "homme"
        self.current = None          # (voice, spk, nom, heure) de la voix qui parle en ce moment
        self.reader = None

        root.title("NOX VF - doublage français")
        root.configure(bg="#070d1f")
        root.geometry("640x720")
        root.minsize(560, 480)
        self._style()
        self._build()
        root.after(100, self._poll_ui)
        root.protocol("WM_DELETE_WINDOW", self.quit)

    # --- interface
    def _style(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure(".", background="#070d1f", foreground="#e6ecff", font=("Segoe UI", 11))
        s.configure("TButton", background="#1a2a52", foreground="white", padding=10, borderwidth=0)
        s.map("TButton", background=[("active", "#26407c")])
        s.configure("Go.TButton", background="#2463eb")
        s.map("Go.TButton", background=[("active", "#3a78ff")])
        s.configure("TCheckbutton", background="#070d1f", foreground="#e6ecff")
        s.configure("TRadiobutton", background="#070d1f", foreground="#e6ecff")
        s.configure("Horizontal.TScale", background="#070d1f")

    def _build(self):
        r = self.root
        tk.Label(r, text="NOX VF", bg="#070d1f", fg="white", font=("Segoe UI Black", 26)).pack(pady=(18, 0))
        tk.Label(r, text="Doublage français en direct pour NOX REMOTE · fait par math_0235",
                 bg="#070d1f", fg="#8fa0cc", font=("Segoe UI", 10)).pack()

        self.status_var = tk.StringVar(value="Arrêté")
        tk.Label(r, textvariable=self.status_var, bg="#101a38", fg="#c8d3f0",
                 font=("Segoe UI", 11), padx=12, pady=8, anchor="w").pack(fill="x", padx=18, pady=14)

        f = tk.Frame(r, bg="#070d1f")
        f.pack(fill="x", padx=18)

        tk.Label(f, text="Voix anglaise en dessous", bg="#070d1f", fg="#e6ecff").grid(row=0, column=0, sticky="w")
        self.duck = tk.IntVar(value=25)
        ttk.Scale(f, from_=0, to=60, variable=self.duck, orient="horizontal", length=260).grid(row=0, column=1, padx=10)
        self.duck_lbl = tk.Label(f, text="25 %", bg="#070d1f", fg="#e6ecff", width=5)
        self.duck_lbl.grid(row=0, column=2)
        self.duck.trace_add("write", lambda *a: self.duck_lbl.config(text=f"{self.duck.get()} %"))

        tk.Label(f, text="Voix française", bg="#070d1f", fg="#e6ecff").grid(row=1, column=0, sticky="w", pady=8)
        self.voice_mode = tk.StringVar(value="auto")
        vf = tk.Frame(f, bg="#070d1f")
        vf.grid(row=1, column=1, columnspan=2, sticky="w", padx=10)
        for txt, val in (("Auto (homme / femme)", "auto"), ("Homme", "homme"), ("Femme", "femme")):
            ttk.Radiobutton(vf, text=txt, value=val, variable=self.voice_mode).pack(side="left", padx=4)

        tk.Label(f, text="Précision", bg="#070d1f", fg="#e6ecff").grid(row=2, column=0, sticky="w")
        self.quality = tk.StringVar(value="small.en")
        qf = tk.Frame(f, bg="#070d1f")
        qf.grid(row=2, column=1, columnspan=2, sticky="w", padx=10)
        for txt, val in (("Rapide", "base.en"), ("Équilibrée", "small.en"), ("Max (PC puissant)", "medium.en")):
            ttk.Radiobutton(qf, text=txt, value=val, variable=self.quality).pack(side="left", padx=4)

        tk.Label(f, text="Texte à doubler", bg="#070d1f", fg="#e6ecff").grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.source = tk.StringVar(value="ecran")
        sf = tk.Frame(f, bg="#070d1f")
        sf.grid(row=5, column=1, columnspan=2, sticky="w", padx=10, pady=(8, 0))
        ttk.Radiobutton(sf, text="Sous-titres du jeu (exact)", value="ecran", variable=self.source).pack(side="left", padx=4)
        ttk.Radiobutton(sf, text="Écoute + traduction IA", value="ecoute", variable=self.source).pack(side="left", padx=4)

        self.auto_persos = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Reconnaître les personnages automatiquement (Jason, Lucia...)",
                        variable=self.auto_persos).grid(row=4, column=0, columnspan=3, sticky="w")

        self.show_subs = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Sous-titres français à l'écran (pour le live)", variable=self.show_subs,
                        command=self._toggle_subs).grid(row=3, column=0, columnspan=3, sticky="w", pady=8)

        b = tk.Frame(r, bg="#070d1f")
        b.pack(pady=8)
        self.go_btn = ttk.Button(b, text="▶  Démarrer le doublage", style="Go.TButton", command=self.toggle)
        self.go_btn.pack(side="left", padx=6)

        pf = tk.Frame(r, bg="#101a38", padx=12, pady=10)
        pf.pack(fill="x", padx=18, pady=(4, 8))
        tk.Label(pf, text="Personnages de l'histoire : la dernière phrase, c'était...", bg="#101a38",
                 fg="#e6ecff").pack(anchor="w")
        pb = tk.Frame(pf, bg="#101a38")
        pb.pack(fill="x", pady=(6, 0))
        ttk.Button(pb, text="Lucia", command=lambda: self.tag_last("Lucia")).pack(side="left", padx=3)
        ttk.Button(pb, text="Jason", command=lambda: self.tag_last("Jason")).pack(side="left", padx=3)
        ttk.Button(pb, text="+ Autre perso", command=self.tag_other).pack(side="left", padx=3)
        ttk.Button(pb, text="Oublier", command=self.reset_persos).pack(side="right", padx=3)
        self.persos_var = tk.StringVar()
        tk.Label(pf, textvariable=self.persos_var, bg="#101a38", fg="#8fa0cc",
                 font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(6, 0))
        self._refresh_persos()

        tk.Label(r, text="Dernières phrases", bg="#070d1f", fg="#8fa0cc").pack(anchor="w", padx=18)
        self.log = tk.Text(r, height=9, bg="#0b1430", fg="#e6ecff", relief="flat", wrap="word",
                           font=("Segoe UI", 10), padx=10, pady=8)
        self.log.pack(fill="both", expand=True, padx=18, pady=(4, 18))
        self.log.tag_config("en", foreground="#7d8bb3")
        self.log.tag_config("fr", foreground="#ffffff")

    def _refresh_persos(self):
        parts = []
        for name, p in self.persos.data.items():
            if name.startswith("_"):
                continue
            parts.append(f"{name} : {p['n']} exemple(s)" if p["n"] else f"{name} : pas encore appris")
        self.persos_var.set("   ·   ".join(parts) +
                            "\nAutomatique : les voix qui reviennent souvent deviennent des persos (Jason, Lucia, Perso 1...)."
                            "\nSi l'IA se trompe, clique sur le bon nom pendant qu'il parle pour la corriger.")

    def tag_last(self, name, gender=None):
        if self.last_emb is None:
            self.status("Attends qu'une phrase soit doublée, puis clique sur le nom du perso.")
            return
        self.persos.add_sample(name, self.last_emb, gender or self.last_gender)
        self._refresh_persos()
        self.status(f"✅ Voix de {name} apprise ({self.persos.data[name]['n']} exemple(s))")

    def tag_other(self):
        from tkinter import simpledialog
        name = simpledialog.askstring(APP, "Nom du personnage :", parent=self.root)
        if name and name.strip():
            self.tag_last(name.strip()[:30])

    def reset_persos(self):
        self.persos.reset()
        self._refresh_persos()
        self.status("Personnages oubliés")

    def _toggle_subs(self):
        if not self.show_subs.get() and self.subs:
            self.subs.destroy()
            self.subs = None

    def _subtitle(self, text):
        if not self.show_subs.get():
            return
        if not self.subs:
            w = tk.Toplevel(self.root)
            w.title("NOX VF - sous-titres")
            w.configure(bg="#000000")
            w.attributes("-topmost", True)
            w.geometry("1000x120+200+800")
            self.subs_lbl = tk.Label(w, text="", bg="#000000", fg="white", wraplength=960,
                                     font=("Segoe UI Semibold", 22), justify="center")
            self.subs_lbl.pack(expand=True, fill="both")
            self.subs = w
        self.subs_lbl.config(text=text)

    def status(self, t):
        self.ui_q.put(("status", t))

    def _poll_ui(self):
        try:
            while True:
                kind, val = self.ui_q.get_nowait()
                if kind == "status":
                    self.status_var.set(val)
                elif kind == "line":
                    en, fr = val
                    self.log.insert("end", en + "\n", "en")
                    self.log.insert("end", "→ " + fr + "\n\n", "fr")
                    self.log.see("end")
                    if int(self.log.index("end").split(".")[0]) > 200:
                        self.log.delete("1.0", "40.0")
                    self._subtitle(fr)
                elif kind == "stopped":
                    self.go_btn.config(text="▶  Démarrer le doublage")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_ui)

    # --- démarrage / arrêt
    def toggle(self):
        if self.running:
            self.running = False
            self.go_btn.config(text="▶  Démarrer le doublage")
            self.status("Arrêté")
            self._send_duck(100)
            try:
                if self.sock:
                    self.sock.close()
            except OSError:
                pass
            return
        self.running = True
        self.go_btn.config(text="■  Arrêter")
        threading.Thread(target=self._start, daemon=True).start()

    def _start(self):
        try:
            if self.engine is None or getattr(self, "_loaded_size", None) != self.quality.get():
                self.engine = Engine(self.status)
                self.engine.load(self.quality.get())
                self._loaded_size = self.quality.get()
        except Exception as e:  # noqa: BLE001
            self.status(f"Erreur de chargement : {e}")
            self.running = False
            self.ui_q.put(("stopped", None))
            return
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._screen_loop, daemon=True).start()
        threading.Thread(target=self._speaker, daemon=True).start()
        self._receiver()

    def _send_line(self, line):
        try:
            if self.sock:
                self.sock.sendall((line + "\n").encode("utf-8"))
        except OSError:
            pass

    def _send_duck(self, pct):
        try:
            if self.sock:
                self.sock.sendall(f"DUCK {int(pct)}\n".encode())
        except OSError:
            pass

    # --- réception du son de NOX REMOTE + découpage en phrases
    def _receiver(self):
        import webrtcvad
        vad = webrtcvad.Vad(2)
        while self.running:
            try:
                self.status("En attente de NOX REMOTE 2 (lance une partie)...")
                self.sock = socket.create_connection((HOST, PORT), timeout=5)
                self.sock.settimeout(None)
                f = self.sock.makefile("rb")
                header = f.readline().decode().split()
                rate, ch = int(header[1]), int(header[2])
                self.status("✅ Connecté - doublage en cours")
                frame_in = int(rate * 0.03) * ch * 2          # 30 ms de son du jeu
                speech, silence, buf16 = [], 0, np.zeros(0, dtype=np.float32)
                while self.running:
                    data = f.read(frame_in)
                    if not data or len(data) < frame_in:
                        break
                    x = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    if ch > 1:
                        x = x.reshape(-1, ch).mean(axis=1)
                    n16 = 480                                   # 30 ms à 16 kHz
                    x16 = np.interp(np.linspace(0, len(x) - 1, n16), np.arange(len(x)), x).astype(np.float32)
                    pcm16 = (np.clip(x16, -1, 1) * 32767).astype(np.int16).tobytes()
                    is_speech = vad.is_speech(pcm16, 16000)
                    if is_speech:
                        speech.append(x16)
                        silence = 0
                    elif speech:
                        speech.append(x16)
                        silence += 1
                    dur = len(speech) * 0.03
                    if speech and (silence >= 17 or dur >= 8.0):   # 0,5 s de silence ou 8 s max
                        seg = np.concatenate(speech)
                        speech, silence = [], 0
                        if dur >= 0.6:
                            try:
                                self.seg_q.put_nowait(seg)
                            except queue.Full:
                                pass                               # on saute si l'IA est en retard
            except (OSError, IndexError, ValueError):
                pass
            finally:
                # NOX REMOTE a coupé la VF (ou la partie est finie) : on se tait tout de suite
                for q in (self.seg_q, self.say_q):
                    try:
                        while True:
                            q.get_nowait()
                    except queue.Empty:
                        pass
                try:
                    import sounddevice as sd
                    sd.stop()
                except Exception:  # noqa: BLE001
                    pass
                if self.running:
                    self.status("VF en pause (désactivée dans NOX REMOTE ou partie terminée)")
                    time.sleep(2)
                try:
                    if self.sock:
                        self.sock.close()
                except OSError:
                    pass
                self.sock = None
        self.ui_q.put(("stopped", None))

    # --- IA : texte anglais -> français
    def _worker(self):
        while self.running:
            try:
                seg = self.seg_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                # musique, chansons, radio : on laisse le son original, pas de doublage
                if self.engine.is_music(seg):
                    continue
                emb = self.engine.embed(seg)
                gender = "femme" if pitch_hz(seg) > 165 else "homme"
                self.last_emb, self.last_gender = emb, gender
                who = self.persos.match(emb)
                if not who and self.auto_persos.get():
                    who = self.persos.auto_learn(emb, gender)
                    if who:
                        self.status(f"🎭 Nouveau personnage reconnu : {who}")
                if who:
                    voice, spk = self.persos.data[who]["voice"]
                    label = who
                    spk_name = who
                else:
                    mode = self.voice_mode.get()
                    voice, spk = (gender if mode == "auto" else mode), None
                    label = "PNJ " + voice
                    spk_name = "Habitante" if voice == "femme" else "Habitant"
                self.current = (voice, spk, spk_name, time.time())
                if self.source.get() == "ecran":
                    continue                       # le texte vient des sous-titres du jeu (_screen_loop)
                en = self.engine.transcribe(seg)
                if len(en) < 2:
                    continue
                fr = self.engine.translate(en)
                self.ui_q.put(("line", (f"[{label}] {en}", fr)))
                try:
                    self.say_q.put_nowait((voice, spk, fr, spk_name))
                except queue.Full:
                    pass
            except Exception as e:  # noqa: BLE001
                self.status(f"Erreur IA : {e}")

    # --- lecture des sous-titres français du jeu à l'écran
    def _screen_loop(self):
        last_seen, stable, last_said = "", 0, ""
        name_check = 0.0
        while self.running:
            time.sleep(0.3)
            if self.source.get() != "ecran" or not self.sock:
                continue
            try:
                if self.reader is None:
                    self.reader = ScreenReader()
                text = self.reader.read_subtitles()
            except Exception as e:  # noqa: BLE001
                self.status(f"Lecture de l'écran impossible : {e} -> passe en « Écoute + traduction IA »")
                time.sleep(5)
                continue
            if not text:
                last_seen, stable = "", 0
                continue
            if same_text(text, last_seen):
                stable += 1
            else:
                last_seen, stable = text, 0
                continue
            # texte stable sur 2 images et nouveau -> on le dit
            if stable != 1 or same_text(text, last_said) or (last_said and text in last_said):
                continue
            last_said = text
            voice, spk, who = "homme", None, "Habitant"
            cur = self.current
            if cur and time.time() - cur[3] < 5:
                voice, spk, who = cur[0], cur[1], cur[2]
            # un nom de perso connu à l'écran (appel, message) ? on prend sa voix
            if time.time() - name_check > 1.5:
                name_check = time.time()
                try:
                    named = self.reader.read_screen_names([n for n in self.persos.data if not n.startswith("_")])
                except Exception:  # noqa: BLE001
                    named = None
                if named and named != who:
                    voice, spk = self.persos.data[named]["voice"]
                    who = named
            self.ui_q.put(("line", (f"[{who}] (sous-titre du jeu)", text)))
            try:
                self.say_q.put_nowait((voice, spk, text, who))
            except queue.Full:
                pass

    # --- voix française + voix anglaise baissée
    def _speaker(self):
        import sounddevice as sd
        while self.running:
            try:
                voice, spk, fr, spk_name = self.say_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                speed = 1.0 + 0.12 * self.say_q.qsize()           # parle un peu plus vite si retard
                pcm, rate = self.engine.speak(voice, fr, min(speed, 1.4), spk)
                self._send_duck(self.duck.get())
                if self.source.get() != "ecran":
                    self._send_line("SUB " + spk_name + "|" + fr.replace("\n", " "))
                sd.play(pcm, rate)
                sd.wait()
            except Exception as e:  # noqa: BLE001
                self.status(f"Erreur voix : {e}")
            finally:
                if self.say_q.empty():
                    self._send_duck(100)
                    self._send_line("SUB")

    def quit(self):
        self.running = False
        self._send_duck(100)
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        root.iconbitmap(os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(__file__)), "noxvf.ico"))
    except tk.TclError:
        pass
    app = NoxVF(root)
    if "--auto" in sys.argv:
        # lancé par le bouton VF de NOX REMOTE : démarre tout seul, fenêtre réduite
        root.after(400, app.toggle)
        root.after(800, root.iconify)
    root.mainloop()


if __name__ == "__main__":
    main()

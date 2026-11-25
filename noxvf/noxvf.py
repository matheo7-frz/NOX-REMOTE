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
    "femme": ("fr_FR-siwis-medium", f"{HF}/siwis/medium/fr_FR-siwis-medium"),
    "homme": ("fr_FR-tom-medium", f"{HF}/tom/medium/fr_FR-tom-medium"),
}
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
        status("Prêt")

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

    def speak(self, name, text, speed):
        """Renvoie (pcm int16 numpy, sample_rate)."""
        voice = self.voices[name]
        chunks, rate = [], 22050
        try:  # piper-tts 1.3+
            from piper import SynthesisConfig
            cfg = SynthesisConfig(length_scale=1.0 / speed)
            for c in voice.synthesize(text, syn_config=cfg):
                chunks.append(c.audio_int16_bytes)
                rate = c.sample_rate
        except (ImportError, TypeError, AttributeError):
            rate = voice.config.sample_rate
            for b in voice.synthesize_stream_raw(text, length_scale=1.0 / speed):
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

        root.title("NOX VF - doublage français")
        root.configure(bg="#070d1f")
        root.geometry("620x560")
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

        self.show_subs = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="Sous-titres français à l'écran (pour le live)", variable=self.show_subs,
                        command=self._toggle_subs).grid(row=3, column=0, columnspan=3, sticky="w", pady=8)

        b = tk.Frame(r, bg="#070d1f")
        b.pack(pady=8)
        self.go_btn = ttk.Button(b, text="▶  Démarrer le doublage", style="Go.TButton", command=self.toggle)
        self.go_btn.pack(side="left", padx=6)

        tk.Label(r, text="Dernières phrases", bg="#070d1f", fg="#8fa0cc").pack(anchor="w", padx=18)
        self.log = tk.Text(r, height=9, bg="#0b1430", fg="#e6ecff", relief="flat", wrap="word",
                           font=("Segoe UI", 10), padx=10, pady=8)
        self.log.pack(fill="both", expand=True, padx=18, pady=(4, 18))
        self.log.tag_config("en", foreground="#7d8bb3")
        self.log.tag_config("fr", foreground="#ffffff")

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
        threading.Thread(target=self._speaker, daemon=True).start()
        self._receiver()

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
                en = self.engine.transcribe(seg)
                if len(en) < 2:
                    continue
                fr = self.engine.translate(en)
                mode = self.voice_mode.get()
                if mode == "auto":
                    mode = "femme" if pitch_hz(seg) > 165 else "homme"
                self.ui_q.put(("line", (en, fr)))
                try:
                    self.say_q.put_nowait((mode, fr))
                except queue.Full:
                    pass
            except Exception as e:  # noqa: BLE001
                self.status(f"Erreur IA : {e}")

    # --- voix française + voix anglaise baissée
    def _speaker(self):
        import sounddevice as sd
        while self.running:
            try:
                mode, fr = self.say_q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                speed = 1.0 + 0.12 * self.say_q.qsize()           # parle un peu plus vite si retard
                pcm, rate = self.engine.speak(mode, fr, min(speed, 1.4))
                self._send_duck(self.duck.get())
                sd.play(pcm, rate)
                sd.wait()
            except Exception as e:  # noqa: BLE001
                self.status(f"Erreur voix : {e}")
            finally:
                if self.say_q.empty():
                    self._send_duck(100)

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

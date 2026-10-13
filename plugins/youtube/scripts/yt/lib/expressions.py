"""expressions — classi di espressione per `yt-portrait scan` (thumbnail v2, knowledge/07-thumbnails.md §10.2).

Niente «massimo di emozione»: ogni frame riceve un'adeguatezza per classe e il foglio mostra i migliori 3 per classe;
decide il pre-test o l'A/B, una classe alla volta (07 §10.2, §15).

Classi (etichette dei fogli in italiano):
  sorriso    sorriso vero, a bocca chiusa o aperta
  risata     sorriso a bocca aperta, denti scoperti
  intenso    bocca chiusa, occhi aperti, sopracciglia aggrottate o sguardo in camera; niente sorriso né labbra serrate
  sorpresa   sopracciglia su, occhi aperti
  neutro     nessun segnale forte (né sorriso, né labbra serrate, né sopracciglia mosse)
  scettico   labbra serrate o arrotolate, smorfia asimmetrica (solo per una leva «contro»)

Due sorgenti di segnale, entrambe locali e solo di analisi (nessun pixel cambia):
  A. geometria dei landmark Apple Vision (`thumbvision score` 1.1+: campo "geom"), sempre disponibile;
     normalizzata per persona e inquadratura con z-score robusti (mediana, MAD) sull'episodio;
  B. MediaPipe Face Landmarker (blendshape, extra facoltativo `install.sh --with-mediapipe`, Apache-2.0):
     sorriso = mouthSmileL/R; Duchenne = sorriso × cheekSquintL/R (AU12 + AU6); denti = mouthUpperUpL/R;
     sopracciglia = max(browInnerUp, browOuterUpL/R); mascella = jawOpen; labbra serrate = mouthPress/mouthRoll;
     parlato = mouthFunnel/mouthPucker; mezzo battito = eyeBlinkL/R; sguardo in camera = 1 − media degli eyeLook*.
     Con B l'appartenenza alla classe la decide B, la forza è 0,7 B + 0,3 A (percentili).

Frame a metà parola: la persona inquadrata sta pronunciando una parola (tempi delle parole e speaker della
trascrizione, se ci sono) con la bocca aperta e senza sorriso, oppure mouthFunnel/mouthPucker alti. Escono dalle
righe delle classi (07 §10.3: smorfia a metà parola = scarto); un sorriso mentre parla resta.
"""
from __future__ import annotations

import bisect
import hashlib
import os
from pathlib import Path

import numpy as np

# Modello ufficiale a revisione fissata: stessi valori di install.sh (MP_URL, MP_SHA, MP_SIZE).
MP_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/"
                "face_landmarker.task")
MP_MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
MP_MODEL_SIZE = 3758596
MP_VERSION = "1.1.0"

CLASSES = ["sorriso", "risata", "intenso", "sorpresa", "neutro", "scettico"]
NON_SCEPTICAL = [c for c in CLASSES if c != "scettico"]
CLASS_HELP = {
    "sorriso": "sorriso vero (bocca chiusa o aperta)",
    "risata": "sorriso a bocca aperta, denti scoperti",
    "intenso": "bocca chiusa, sguardo concentrato (sopracciglia giù o in camera)",
    "sorpresa": "sopracciglia su, occhi aperti",
    "neutro": "nessun segnale forte",
    "scettico": "labbra serrate o smorfia asimmetrica: solo per una leva «contro»",
}
# leva → classi adatte (07 §5, tabella espressione ↔ leva; TheCraigHewitt [aneddotico])
LEVER_CLASSES = {"contro": ["scettico", "intenso"], "risultato": ["sorriso", "sorpresa"], "numero": ["sorriso", "sorpresa"],
                 "storia": ["intenso", "neutro"], "claim": ["intenso", "sorriso"], "duo": ["sorriso", "risata", "sorpresa"]}


# ── MediaPipe ───────────────────────────────────────────────────────────────
def mp_model_path() -> Path:
    if os.environ.get("YT_MP_MODEL"):
        return Path(os.environ["YT_MP_MODEL"]).expanduser()
    import ytcore  # noqa: PLC0415
    return Path(ytcore.PLUGIN_DATA) / "models" / "mediapipe" / "face_landmarker.task"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def mp_status(check_sha: bool = True) -> dict:
    """{ok, version, model, reason}: senza importare mediapipe (lento), solo metadati del pacchetto + modello."""
    import importlib.metadata as md  # noqa: PLC0415
    try:
        version = md.version("mediapipe")
    except md.PackageNotFoundError:
        return {"ok": False, "version": None, "model": str(mp_model_path()),
                "reason": "mediapipe non installato nel venv del plugin (install.sh --yes --with-mediapipe)"}
    model = mp_model_path()
    if not model.is_file():
        return {"ok": False, "version": version, "model": str(model), "reason": f"modello assente ({model}): install.sh --yes --with-mediapipe"}
    if check_sha and sha256_file(model) != MP_MODEL_SHA256:
        return {"ok": False, "version": version, "model": str(model), "reason": "SHA256 del modello diverso da quello fissato: rilancia install.sh --with-mediapipe"}
    return {"ok": True, "version": version, "model": str(model), "reason": ""}


class MPRunner:
    """FaceLandmarker in modalità IMAGE, un volto, solo blendshape. Il volto va passato già ritagliato (box Vision ×2,2):
    il rilevatore di MediaPipe è pensato per volti vicini e così non sceglie mai la persona accanto."""

    def __init__(self, model: Path):
        import absl.logging  # noqa: PLC0415
        absl.logging.set_verbosity(absl.logging.ERROR)
        os.environ.setdefault("GLOG_minloglevel", "2")
        import mediapipe as mp  # noqa: PLC0415
        from mediapipe.tasks import python as mpt  # noqa: PLC0415
        from mediapipe.tasks.python import vision  # noqa: PLC0415
        self.mp = mp
        opts = vision.FaceLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=str(model)),
                                            output_face_blendshapes=True, num_faces=1,
                                            running_mode=vision.RunningMode.IMAGE)
        self.lm = vision.FaceLandmarker.create_from_options(opts)
        self.version = getattr(mp, "__version__", "?")

    def blendshapes(self, rgb: np.ndarray, box_px: list[float] | None = None, grow: float = 2.2) -> dict | None:
        if box_px is not None:
            x, y, w, h = box_px
            s = max(w, h) * grow
            cx, cy = x + w / 2, y + h / 2
            y0, y1 = int(max(0, cy - s / 2)), int(min(rgb.shape[0], cy + s / 2))
            x0, x1 = int(max(0, cx - s / 2)), int(min(rgb.shape[1], cx + s / 2))
            rgb = rgb[y0:y1, x0:x1]
        if rgb.shape[0] < 32 or rgb.shape[1] < 32:
            return None
        res = self.lm.detect(self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb[..., :3])))
        if not res.face_blendshapes:
            return None
        return {c.category_name: round(float(c.score), 4) for c in res.face_blendshapes[0]}

    def close(self, timeout: float = 2.0) -> bool:
        """Chiude il landmarker senza bloccare la scansione: in mediapipe 1.1.0 la chiusura attende il thread del
        dispatcher, che sulla scansione di una camera intera ha impiegato fino a 23 s. Ritorna True se ha chiuso in tempo."""
        import threading  # noqa: PLC0415

        def _close() -> None:
            try:
                self.lm.close()
            except Exception:  # noqa: BLE001
                pass
        th = threading.Thread(target=_close, daemon=True)
        th.start()
        th.join(timeout)
        return not th.is_alive()


def mp_signals(bs: dict | None) -> dict | None:
    """Segnali derivati 0–1 dai 52 blendshape."""
    if not bs:
        return None
    g = lambda *k: float(np.mean([bs.get(x, 0.0) for x in k]))  # noqa: E731
    smile = g("mouthSmileLeft", "mouthSmileRight")
    cheek = g("cheekSquintLeft", "cheekSquintRight")
    looks = ["eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight",
             "eyeLookUpLeft", "eyeLookUpRight", "eyeLookDownLeft", "eyeLookDownRight"]
    return {
        "smile": round(smile, 4), "cheek": round(cheek, 4), "duchenne": round(smile * cheek, 4),
        "teeth": round(g("mouthUpperUpLeft", "mouthUpperUpRight"), 4),
        "smile_asym": round(abs(bs.get("mouthSmileLeft", 0) - bs.get("mouthSmileRight", 0)), 4),
        "brow": round(max(bs.get("browInnerUp", 0.0), g("browOuterUpLeft", "browOuterUpRight")), 4),
        "brow_down": round(g("browDownLeft", "browDownRight"), 4),
        "eye_wide": round(g("eyeWideLeft", "eyeWideRight"), 4),
        "eye_squint": round(g("eyeSquintLeft", "eyeSquintRight"), 4),
        "blink": round(g("eyeBlinkLeft", "eyeBlinkRight"), 4),
        "jaw": round(bs.get("jawOpen", 0.0), 4),
        "press": round(max(g("mouthPressLeft", "mouthPressRight"), g("mouthRollLower", "mouthRollUpper")), 4),
        "speech": round(max(bs.get("mouthFunnel", 0.0), bs.get("mouthPucker", 0.0)), 4),
        "frown": round(g("mouthFrownLeft", "mouthFrownRight"), 4),
        "gaze_cam": round(1 - g(*looks), 4),
    }


# ── Trascrizione: chi parla e quando ────────────────────────────────────────
class Words:
    """Tempi delle parole per speaker (transcript.words.json di yt-transcribe), sul tempo del master."""

    def __init__(self, words: list[dict], offset: float = 0.0):
        self.by: dict[str, tuple[list[float], list[float]]] = {}
        for w in words:
            if w.get("start") is None or w.get("end") is None:
                continue
            spk = str(w.get("speaker") or "?")
            s, e = self.by.setdefault(spk, ([], []))
            s.append(float(w["start"]) - offset)
            e.append(float(w["end"]) - offset)
        for spk, (s, e) in self.by.items():
            order = np.argsort(s)
            self.by[spk] = ([s[i] for i in order], [e[i] for i in order])
        self.speakers = sorted(self.by)

    @classmethod
    def load(cls, workdir: Path | None, offset: float = 0.0) -> "Words | None":
        if not workdir:
            return None
        p = Path(workdir) / "analysis" / "transcript.words.json"
        if not p.exists():
            return None
        import json  # noqa: PLC0415
        try:
            d = json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            return None
        words = d.get("words") if isinstance(d, dict) else d
        return cls(words or [], offset) if words else None

    def speaking(self, t: float, spk: str, margin: float = 0.03) -> bool:
        s, e = self.by.get(spk, ([], []))
        i = bisect.bisect_right(s, t + margin) - 1
        return i >= 0 and s[i] + margin <= t <= e[i] - margin

    def anyone(self, t: float) -> str | None:
        for spk in self.speakers:
            if self.speaking(t, spk, 0.0):
                return spk
        return None


def active_speaker(recs: list[dict], words: Words | None) -> dict:
    """Chi è la persona inquadrata: lo speaker la cui voce coincide di più con la bocca in movimento
    (media di mouth_open quando parla lui − quando non parla). Senza trascrizione: nessuno."""
    if not words or len(recs) < 30:
        return {"speaker": None, "evidence": {}}
    mo = np.array([r["face"].get("mouth_open") or 0.0 for r in recs])
    ev = {}
    for spk in words.speakers:
        on = np.array([words.speaking(r["t"], spk, 0.0) for r in recs])
        if on.sum() < 10 or (~on).sum() < 10:
            continue
        ev[spk] = round(float(mo[on].mean() - mo[~on].mean()), 4)
    if not ev:
        return {"speaker": None, "evidence": ev}
    best = max(ev, key=ev.get)
    return {"speaker": best if ev[best] > 0.05 else None, "evidence": ev}


# ── Statistiche robuste ─────────────────────────────────────────────────────
def robust_z(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, float)
    ok = np.isfinite(v)
    if ok.sum() < 5:
        return np.zeros_like(v)
    med = float(np.median(v[ok]))
    mad = float(np.median(np.abs(v[ok] - med))) * 1.4826
    if mad < 1e-9:
        mad = float(np.std(v[ok])) or 1.0
    z = (v - med) / mad
    return np.where(ok, np.clip(z, -6, 6), 0.0)


def pct_rank(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, float)
    if len(v) < 2:
        return np.ones(len(v))
    return v.argsort().argsort() / (len(v) - 1)


GEOM_KEYS = ["mouth_w", "smile_lift", "nose_lip", "lip_thick", "brow_mean", "brow_inner", "corner_asym", "brow_asym"]


def vision_signals(recs: list[dict]) -> None:
    """r["vz"]: segnali Vision z-normalizzati sul gruppo (stessa persona e stessa inquadratura)."""
    def col(key: str, absval: bool = False) -> np.ndarray:
        out = []
        for r in recs:
            g = (r["face"].get("geom") or {}).get(key)
            out.append(np.nan if g is None else (abs(g) if absval else g))
        return np.array(out, float)
    z = {k: robust_z(col(k, absval=k in ("corner_asym",))) for k in GEOM_KEYS}
    z["eye"] = robust_z(np.array([r["face"].get("eye_ratio") if r["face"].get("eye_ratio") is not None else np.nan for r in recs]))
    for i, r in enumerate(recs):
        has = bool(r["face"].get("geom"))
        smile = 0.40 * z["mouth_w"][i] + 0.25 * z["smile_lift"][i] - 0.20 * z["nose_lip"][i] - 0.15 * z["eye"][i]
        brow = 0.6 * z["brow_mean"][i] + 0.4 * z["brow_inner"][i]
        r["vz"] = {"ok": has, "smile": round(float(smile), 3), "brow": round(float(brow), 3), "lip": round(float(z["lip_thick"][i]), 3),
                   "asym": round(float(max(z["corner_asym"][i], z["brow_asym"][i])), 3), "eye": round(float(z["eye"][i]), 3),
                   "mouth_open": float(r["face"].get("mouth_open") or 0.0)}


def mid_word(r: dict, words: Words | None, speaker: str | None) -> tuple[bool, str]:
    """(a metà parola?, motivo)."""
    vz, m = r.get("vz") or {}, r.get("mps")
    smiling = (m["smile"] >= 0.4) if m else (vz.get("smile", 0) >= 0.8)
    if m and m["speech"] >= 0.4 and not smiling:
        return True, f"labbra a «o/u» (mouthFunnel/Pucker {m['speech']:.2f})"
    open_ = vz.get("mouth_open", 0) >= 0.25 or (m is not None and m["jaw"] >= 0.12)
    if words and speaker:
        if words.speaking(r["t"], speaker) and open_ and not smiling:
            return True, f"{speaker} sta parlando (tempi delle parole) a bocca aperta"
        return False, ""
    if vz.get("mouth_open", 0) >= 0.5 and not smiling:
        return True, "bocca aperta senza sorriso (nessuna trascrizione: stima)"
    return False, ""


def class_strengths(r: dict) -> dict[str, float | None]:
    """Forza per classe (None = non membro). Con MediaPipe decide MediaPipe, altrimenti la geometria Vision."""
    vz, m = r.get("vz") or {}, r.get("mps")
    mo = vz.get("mouth_open", 0.0)
    out: dict[str, float | None] = {c: None for c in CLASSES}
    if m:
        closed = mo < 0.2 and m["jaw"] < 0.1
        if m["smile"] >= 0.45:
            out["sorriso"] = m["smile"] + 0.5 * m["duchenne"] + 0.3 * m["teeth"]
        if m["smile"] >= 0.5 and (m["teeth"] >= 0.4 or mo >= 0.6 or m["jaw"] >= 0.25):
            out["risata"] = m["smile"] * max(m["teeth"], m["jaw"], mo)
        mz = r.get("mpz") or {}
        focus = max(mz.get("brow_down", 0.0), mz.get("gaze_cam", 0.0) - 0.5)   # sopracciglia aggrottate o sguardo in camera
        if closed and m["smile"] < 0.25 and m["press"] < 0.3 and m["blink"] < 0.5 and focus >= 0.5:
            out["intenso"] = (1 - m["smile"]) * (1 - m["press"]) * (1 + min(focus, 3.0) / 3)
        if m["brow"] >= 0.25 and m["blink"] < 0.5:
            out["sorpresa"] = m["brow"] + 0.5 * m["eye_wide"]
        if m["smile"] < 0.15 and m["press"] < 0.2 and m["brow"] < 0.15 and m["jaw"] < 0.15 and focus < 0.5:
            out["neutro"] = 1 - max(m["smile"], m["press"], m["brow"], m["jaw"])
        if (m["press"] >= 0.3 and m["smile"] < 0.3) or (m["smile_asym"] >= 0.25 and m["smile"] < 0.4):
            out["scettico"] = m["press"] + m["smile_asym"]
        return out
    if not vz.get("ok"):
        return out
    s, b, lip, asym, eye = vz["smile"], vz["brow"], vz["lip"], vz["asym"], vz["eye"]
    if s >= 1.0:
        out["sorriso"] = s
    if s >= 1.0 and mo >= 0.6:
        out["risata"] = s + mo
    if mo < 0.15 and abs(s) < 0.8 and lip > -1.0 and b <= -0.5 and eye >= -0.5:        # sopracciglia abbassate
        out["intenso"] = 1.0 - abs(s) / 2 - b / 2 + 0.2 * eye
    if b >= 1.2 and eye >= 0:
        out["sorpresa"] = b + 0.5 * eye
    if mo < 0.2 and max(abs(s), abs(b), abs(lip)) < 0.7 and b > -0.5:
        out["neutro"] = 1.0 - max(abs(s), abs(b), abs(lip))
    if (mo < 0.15 and lip <= -1.0) or asym >= 1.8:
        out["scettico"] = max(-lip, asym)
    return out


def vision_strengths(r: dict) -> dict[str, float]:
    """Forza Vision per classe (anche fuori soglia), per il 30 % della forza combinata."""
    vz = r.get("vz") or {}
    if not vz.get("ok"):
        return {c: 0.0 for c in CLASSES}
    s, b, lip, asym, mo = vz["smile"], vz["brow"], vz["lip"], vz["asym"], vz["mouth_open"]
    return {"sorriso": s, "risata": s + mo, "intenso": -abs(s) - max(0.0, -lip) + (1 - mo), "sorpresa": b,
            "neutro": -max(abs(s), abs(b), abs(lip)), "scettico": max(-lip, asym)}


def classify(recs: list[dict], words: Words | None, speaker: str | None) -> dict:
    """Aggiunge a ogni record: vz, mid_word, classes {classe: forza 0–1 combinata}. Ritorna statistiche."""
    vision_signals(recs)
    mpr = [r for r in recs if r.get("mps")]
    if len(mpr) >= 20:                   # intensità relative alla persona (occhiali e barba spostano i valori assoluti)
        zb = robust_z(np.array([r["mps"]["brow_down"] for r in mpr]))
        zg = robust_z(np.array([r["mps"]["gaze_cam"] for r in mpr]))
        for r, a, b in zip(mpr, zb, zg):
            r["mpz"] = {"brow_down": round(float(a), 3), "gaze_cam": round(float(b), 3)}
    n_mid = 0
    raw: dict[str, list[tuple[int, float]]] = {c: [] for c in CLASSES}
    for i, r in enumerate(recs):
        mw, why = mid_word(r, words, speaker)
        r["mid_word"] = mw
        if mw:
            r["mid_word_why"] = why
            n_mid += 1
        for c, v in class_strengths(r).items():
            if v is not None:
                raw[c].append((i, float(v)))
    vs = [vision_strengths(r) for r in recs]
    for r in recs:
        r["classes"] = {}
    for c, members in raw.items():
        if not members:
            continue
        idx = [i for i, _ in members]
        p_main = pct_rank(np.array([v for _, v in members]))
        if any(recs[i].get("mps") for i in idx):
            p_vis = pct_rank(np.array([vs[i][c] for i in idx]))
            comb = 0.7 * p_main + 0.3 * p_vis
        else:
            comb = p_main
        for k, i in enumerate(idx):
            recs[i]["classes"][c] = round(float(comb[k]), 4)
    return {"mid_word": n_mid, "members": {c: len(v) for c, v in raw.items()}}


# Pesi del ranking per classe (07 §10.2; da calibrare su 10 frame etichettati, 07 §10.4)
W_RANK = {"q": 0.20, "sh": 0.20, "mo": 0.10, "fr": 0.15, "ey": 0.10, "fp": 0.10, "fit": 0.15}
PEN_MID, PEN_SCEPT = 0.15, 0.10


def rank_class(recs: list[dict], P: dict[str, np.ndarray], cls: str, allowed: set[int]) -> list[tuple[int, float]]:
    """[(indice, punteggio)] dei membri della classe, metà parola esclusi, scartati esclusi (allowed)."""
    out = []
    for i, r in enumerate(recs):
        fit = (r.get("classes") or {}).get(cls)
        if fit is None or i not in allowed or r.get("mid_word"):
            continue
        s = (W_RANK["q"] * P["q"][i] + W_RANK["sh"] * P["sh"][i] + W_RANK["mo"] * P["mo"][i] + W_RANK["fr"] * P["fr"][i]
             + W_RANK["ey"] * P["ey"][i] + W_RANK["fp"] * P["fp"][i] + W_RANK["fit"] * fit)
        if cls != "scettico" and "scettico" in (r.get("classes") or {}):
            s -= PEN_SCEPT
        out.append((i, round(float(s), 4)))
    out.sort(key=lambda x: -x[1])
    return out


def stability(a: dict | None, b: dict | None) -> dict | None:
    """Variabilità n → n+1 dei segnali MediaPipe (|Δ|), dichiarata nel log (criterio E1)."""
    if not a or not b:
        return None
    keys = ("smile", "teeth", "brow", "jaw", "press", "blink", "speech")
    return {k: round(abs(a[k] - b[k]), 4) for k in keys}


# ── Autotest (yt-portrait selftest) ─────────────────────────────────────────
def selftest() -> list[tuple[str, bool, str]]:
    res = []
    z = robust_z(np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 100.0]))
    res.append(("robust_z: outlier non schiaccia gli altri", bool(z[-1] == 6 and abs(z[4]) < 1), f"z={np.round(z, 2).tolist()}"))
    w = Words([{"start": 1.0, "end": 1.5, "speaker": "S0"}, {"start": 2.0, "end": 2.4, "speaker": "S1"}])
    res.append(("Words.speaking", w.speaking(1.2, "S0") and not w.speaking(1.2, "S1") and not w.speaking(1.8, "S0"), ""))
    base = {"smile": 0.0, "cheek": 0.0, "duchenne": 0.0, "teeth": 0.0, "smile_asym": 0.0, "brow": 0.0, "brow_down": 0.0,
            "eye_wide": 0.0, "eye_squint": 0.0, "blink": 0.2, "jaw": 0.0, "press": 0.0, "speech": 0.0, "frown": 0.0, "gaze_cam": 0.6}
    smile = {"t": 1.2, "face": {"mouth_open": 0.9}, "vz": {"ok": True, "smile": 2.0, "brow": 0, "lip": 0, "asym": 0, "eye": -1, "mouth_open": 0.9},
             "mps": {**base, "smile": 0.73, "teeth": 0.67}}
    talk = {"t": 1.2, "face": {"mouth_open": 0.9}, "vz": {"ok": True, "smile": 0.0, "brow": 0, "lip": 0, "asym": 0, "eye": 0, "mouth_open": 0.9},
            "mps": {**base, "jaw": 0.3}}
    press = {"t": 3.0, "face": {"mouth_open": 0.0}, "vz": {"ok": True, "smile": 0.0, "brow": 0, "lip": -1.5, "asym": 0, "eye": 0, "mouth_open": 0.0},
             "mps": {**base, "press": 0.4}}
    cs = class_strengths(smile)
    res.append(("classe: sorriso aperto = sorriso + risata", cs["sorriso"] is not None and cs["risata"] is not None and cs["scettico"] is None, str(cs)))
    res.append(("classe: labbra serrate = scettico, non intenso", class_strengths(press)["scettico"] is not None
                and class_strengths(press)["intenso"] is None, ""))
    calm = {"t": 5.0, "face": {"mouth_open": 0.0}, "vz": {"ok": True, "smile": 0.0, "brow": 0, "lip": 0, "asym": 0, "eye": 0, "mouth_open": 0.0},
            "mps": dict(base)}
    focus = {**calm, "mpz": {"brow_down": 1.2, "gaze_cam": 0.0}}
    res.append(("classe: bocca chiusa calma = neutro, aggrottata = intenso",
                class_strengths(calm)["neutro"] is not None and class_strengths(calm)["intenso"] is None
                and class_strengths(focus)["intenso"] is not None and class_strengths(focus)["neutro"] is None, ""))
    res.append(("metà parola: chi parla a bocca aperta senza sorriso", mid_word(talk, w, "S0")[0], mid_word(talk, w, "S0")[1]))
    res.append(("metà parola: il sorriso mentre parla resta", not mid_word(smile, w, "S0")[0], ""))
    res.append(("metà parola: se parla un altro, ascolta", not mid_word(talk, w, "S1")[0], ""))
    sv = {k: 0.0 for k in GEOM_KEYS}
    recs = [{"t": float(i), "face": {"mouth_open": 0.0, "eye_ratio": 0.22, "geom": {**sv, "mouth_w": 0.9 + 0.01 * (i % 5)}}} for i in range(40)]
    recs[7]["face"]["geom"]["mouth_w"] = 1.2
    recs[7]["face"]["mouth_open"] = 0.9
    classify(recs, None, None)
    res.append(("Vision: bocca larga z alto → sorriso (senza MediaPipe)", "sorriso" in recs[7]["classes"], str(recs[7]["vz"])))
    return res

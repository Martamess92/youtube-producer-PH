#!/usr/bin/env python3
"""yt-loudnorm — loudness EBU R128 a due passaggi + bilanciamento L/R.

Catena: (bilanciamento L/R) → (catena gentile opzionale: highpass 80 Hz + compressione leggera)
→ loudnorm passo 1 (misura) → loudnorm passo 2 (lineare quando possibile) → verifica ebur128.

Bilanciamento (`--balance`):
- `none`   nessun intervento sui canali.
- `auto`   analizza i canali e sceglie (scelta spiegata nel report):
    · canale muto/quasi muto            → mono dal canale attivo
    · un canale è solo una copia più bassa dell'altro (correlazione ≥0.95, ritardo ~0)
                                         → mono dal canale più forte (niente comb filter)
    · due microfoni su due canali (ognuno domina >6 dB in ≥5% del parlato, es. un podcast con
      L = microfono a mano del conduttore, R = lavalier dell'ospite, con rientro reciproco)
                                         → automix mono a gain-sharing (tipo Dugan), con
                                           allineamento del livello dei due microfoni
    · squilibrio >3 dB su segnali diversi → ribilanciamento con pan, stereo conservato
    · altrimenti                         → nessun intervento
- `mono`   come auto ma il risultato è sempre mono (consigliato per podcast parlati).
- Forzature esplicite: `automix`, `left`, `right`, `average`, `rebalance`.
Il mono viene scritto come stereo dual-mono (2 canali identici) salvo `--channels 1`.

Importabile da altri comandi: `normalize()`, `analyze_balance()`, `decide_balance()`,
`render_balanced()`, `measure_ebur128()`.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ytcore as yc  # noqa: E402

import numpy as np  # noqa: E402

SR_OUT = 48000
ANALYSIS_SR = 8000            # analisi canali: banda vocale, veloce
FINE_SEC = 0.010              # griglia inviluppo automix (10 ms)
BLOCK_SEC = 0.5               # blocchi per dominanza/livelli
CHUNK_SEC = 10.0              # finestre di correlazione e chunk di lettura
IMBALANCE_DB = 3.0            # soglia squilibrio (task/design)
DOMINANCE_DB = 6.0            # un canale "domina" un blocco se più forte di 6 dB
DOMINANCE_FRAC = 0.05         # ...in almeno il 5% dei blocchi attivi (per ciascun lato)
COPY_CORR = 0.95              # correlazione per dire "copia attenuata"
GENTLE_CHAIN = ["highpass=f=80", "acompressor=threshold=0.125:ratio=2:attack=20:release=250:makeup=1"]
EXPLICIT_MODES = ("automix", "left", "right", "average", "rebalance")
BALANCE_MODES = ("auto", "mono", "none") + EXPLICIT_MODES
REPORT_VERSION = 3
# Riempie i buchi di timestamp con silenzio (es. pacchetti AAC con durata anomala in un proxy,
# o pacchetti scartati dal decoder AAC nativo): senza, l'audio decodificato "si accorcia"
# e va fuori sync col video. Unica definizione in ytcore.
ASYNC = yc.AUDIO_ASYNC


# ── Probe e decodifica ──────────────────────────────────────────────────────
def probe_audio(path: Path | str) -> dict:
    """Primo stream audio: codec, canali, sample rate, durata (anche da file video)."""
    info = yc.ffprobe(path)
    streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not streams:
        raise ValueError(f"Nessuna traccia audio in {path}")
    a = streams[0]
    dur = a.get("duration") or info.get("format", {}).get("duration") or 0
    return {"codec": a.get("codec_name"), "channels": int(a.get("channels") or 0),
            "sample_rate": int(a.get("sample_rate") or 0), "layout": a.get("channel_layout"),
            "duration": float(dur), "path": str(path)}


def decoder_args(info: dict, workdir: Path | str | None = None) -> list[str]:
    """Decoder per l'ingresso: policy centrale ytcore.aac_decoder_args (AAC → nativo float, salvo
    decisione aac_at del progetto o forzatura YT_AAC_DECODER; non AAC → nessun argomento).
    Senza workdir la cartella di lavoro si ricava dal percorso in `info` (vedi probe_audio)."""
    return yc.aac_decoder_args(workdir, info)


def _ff_input(path: Path | str, info: dict) -> list[str]:
    return [*decoder_args(info), "-i", str(path)]


def _decode_chunks(path: Path | str, info: dict, sr: int, channels: int, chunk_frames: int):
    """Genera blocchi float32 (frame × canali) decodificati da ffmpeg in streaming."""
    cmd = [yc.FFMPEG, "-hide_banner", "-nostdin", "-v", "error", *_ff_input(path, info),
           "-map", "0:a:0", "-vn", "-af", ASYNC, "-ac", str(channels), "-ar", str(sr), "-f", "f32le", "-"]
    yc.log("$", " ".join(yc._q(str(c)) for c in cmd))
    with tempfile.TemporaryFile() as errf:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf)
        bytes_per = 4 * channels * chunk_frames
        try:
            while True:
                buf = proc.stdout.read(bytes_per)
                if not buf:
                    break
                usable = len(buf) - len(buf) % (4 * channels)
                yield np.frombuffer(buf[:usable], dtype=np.float32).reshape(-1, channels)
        finally:
            proc.stdout.close()
            rc = proc.wait()
            if rc != 0:
                errf.seek(0)
                raise RuntimeError(f"Decodifica fallita ({rc}): {errf.read().decode(errors='replace')[-1500:]}")


def _db(p: float | np.ndarray, floor: float = 1e-12):
    return 10 * np.log10(np.maximum(p, floor))


# ── Analisi canali ──────────────────────────────────────────────────────────
def _xcorr_peak(l: np.ndarray, r: np.ndarray, maxlag: int) -> tuple[int, float]:
    """Picco della correlazione normalizzata L↔R entro ±maxlag campioni."""
    n = 1 << int(math.ceil(math.log2(len(l) * 2)))
    c = np.fft.irfft(np.fft.rfft(l, n) * np.conj(np.fft.rfft(r, n)), n)
    c = np.concatenate([c[-maxlag:], c[:maxlag + 1]])
    den = math.sqrt(float((l * l).sum()) * float((r * r).sum())) or 1.0
    k = int(np.argmax(np.abs(c)))
    return k - maxlag, float(c[k] / den)


def analyze_balance(path: Path | str, info: dict | None = None) -> dict:
    """Misura i due canali (8 kHz, streaming): livelli, squilibrio, dominanza per blocchi,
    correlazione/ritardo L↔R. Le serie fini (10 ms) restano in `_fine` per l'automix."""
    info = info or probe_audio(path)
    t0 = time.time()
    if info["channels"] < 2:
        return {"channels": info["channels"], "note": "sorgente mono", "elapsed_s": 0.0}
    fine = int(round(ANALYSIS_SR * FINE_SEC))
    chunk = int(ANALYSIS_SR * CHUNK_SEC)
    eL, eR, corrs = [], [], []
    sumL = sumR = 0.0
    nsamp = 0
    for block in _decode_chunks(path, info, ANALYSIS_SR, 2, chunk):
        L = block[:, 0].astype(np.float64)
        R = block[:, 1].astype(np.float64)
        sumL += float((L * L).sum())
        sumR += float((R * R).sum())
        nsamp += len(L)
        m = len(L) // fine
        if m:
            eL.append((L[: m * fine] ** 2).reshape(m, fine).mean(1))
            eR.append((R[: m * fine] ** 2).reshape(m, fine).mean(1))
        if len(L) >= ANALYSIS_SR:  # correlazione su finestre da 10 s (±10 ms)
            lag, c = _xcorr_peak(L, R, int(ANALYSIS_SR * 0.010))
            corrs.append((lag, c, float((L * L).sum() + (R * R).sum())))
    if nsamp == 0:
        raise ValueError(f"Audio vuoto: {path}")
    eL = np.concatenate(eL) if eL else np.zeros(1)
    eR = np.concatenate(eR) if eR else np.zeros(1)

    # blocchi da 0.5 s per dominanza e livelli del parlato
    k = int(round(BLOCK_SEC / FINE_SEC))
    nb = len(eL) // k
    pL = eL[: nb * k].reshape(nb, k).mean(1) if nb else eL
    pR = eR[: nb * k].reshape(nb, k).mean(1) if nb else eR
    dL, dR = _db(pL), _db(pR)
    loud = np.maximum(dL, dR)
    ref = float(np.percentile(loud, 95)) if len(loud) else -100.0
    active = loud > max(ref - 30.0, -70.0)
    diff = (dL - dR)[active]
    frac_L = float((diff > DOMINANCE_DB).mean()) if diff.size else 0.0
    frac_R = float((diff < -DOMINANCE_DB).mean()) if diff.size else 0.0
    domL = dL[active][diff > DOMINANCE_DB]
    domR = dR[active][diff < -DOMINANCE_DB]

    # correlazione: mediana pesata sull'energia delle finestre attive
    corr_med, lag_med = None, None
    if corrs:
        energies = np.array([c[2] for c in corrs])
        keep = energies >= np.percentile(energies, 25)
        sel = [c for c, kk in zip(corrs, keep) if kk] or corrs
        cs = np.array([abs(c[1]) for c in sel])
        lags = np.array([c[0] for c in sel])
        corr_med = float(np.median(cs))
        lag_med = float(np.median(lags)) / ANALYSIS_SR * 1000

    rmsL = float(_db(sumL / nsamp))
    rmsR = float(_db(sumR / nsamp))
    act_pow_L = float(pL[active].sum()) if active.any() else sumL
    act_pow_R = float(pR[active].sum()) if active.any() else sumR
    return {
        "channels": info["channels"],
        "duration": round(nsamp / ANALYSIS_SR, 3),
        "rms_db": {"L": round(rmsL, 2), "R": round(rmsR, 2)},
        "diff_db": round(rmsL - rmsR, 2),
        "diff_active_db": round(float(_db(act_pow_L) - _db(act_pow_R)), 2),
        "active_fraction": round(float(active.mean()), 3) if len(active) else 0.0,
        "dominance": {"L_frac": round(frac_L, 3), "R_frac": round(frac_R, 3), "threshold_db": DOMINANCE_DB},
        "dominant_level_db": {"L": round(float(np.median(domL)), 2) if domL.size else None,
                              "R": round(float(np.median(domR)), 2) if domR.size else None},
        "xcorr": {"median_abs": None if corr_med is None else round(corr_med, 3),
                  "median_lag_ms": None if lag_med is None else round(lag_med, 2),
                  "windows": len(corrs)},
        "elapsed_s": round(time.time() - t0, 2),
        "_fine": {"eL": eL, "eR": eR, "step": FINE_SEC},
    }


def decide_balance(m: dict, mode: str = "auto") -> dict:
    """Sceglie l'intervento sui canali. Ritorna {decision, reason, gains_db?}."""
    if mode == "none":
        return {"decision": "keep", "reason": "--balance none: canali non toccati"}
    if m.get("channels", 2) < 2:
        return {"decision": "mono-input", "reason": "sorgente mono: duplicata su L/R"}
    if mode in EXPLICIT_MODES:
        d = {"decision": mode, "reason": f"forzato da --balance {mode}"}
        if mode == "rebalance":
            d["gains_db"] = {"L": round(-m["diff_active_db"] / 2, 2), "R": round(m["diff_active_db"] / 2, 2)}
        if mode == "automix":
            d["gains_db"] = _automix_gains(m)
        return d

    diff = m["diff_active_db"]
    rms = m["rms_db"]
    xc = m["xcorr"]["median_abs"] or 0.0
    lag = abs(m["xcorr"]["median_lag_ms"] or 0.0)
    fl, fr = m["dominance"]["L_frac"], m["dominance"]["R_frac"]
    louder = "left" if diff > 0 else "right"
    side_it = {"left": "sinistro (L)", "right": "destro (R)"}

    if min(rms["L"], rms["R"]) < -60 or abs(diff) > 30:
        return {"decision": louder,
                "reason": f"canale {'R' if louder == 'left' else 'L'} muto o quasi ({rms}); "
                          f"mono dal canale {side_it[louder]}"}
    if xc >= COPY_CORR and lag <= 0.25:
        if abs(diff) > IMBALANCE_DB:
            return {"decision": louder,
                    "reason": f"L e R sono lo stesso segnale (correlazione {xc:.2f}, ritardo {lag:.2f} ms) "
                              f"con {abs(diff):.1f} dB di differenza: il canale più basso è solo una copia "
                              f"attenuata → mono dal canale {side_it[louder]} (sommare non aggiunge nulla)"}
        return {"decision": "keep" if mode == "auto" else "average",
                "reason": f"L e R praticamente identici (correlazione {xc:.2f}, Δ {diff:+.1f} dB): già mono"}
    if fl >= DOMINANCE_FRAC and fr >= DOMINANCE_FRAC:
        return {"decision": "automix", "gains_db": _automix_gains(m),
                "reason": f"due microfoni su due canali: L domina (>{DOMINANCE_DB:.0f} dB) nel {fl:.0%} del "
                          f"parlato, R nel {fr:.0%}; i canali si rientrano a vicenda (correlazione "
                          f"{xc:.2f}, ritardo {lag:.1f} ms) quindi NON sono copie: tenere solo il più forte "
                          f"perderebbe un interlocutore e la somma semplice crea comb filter. → automix mono "
                          f"a gain-sharing con livelli dei microfoni allineati, uscita dual-mono"}
    if abs(diff) > IMBALANCE_DB:
        g = {"L": round(-diff / 2, 2), "R": round(diff / 2, 2)}
        if mode == "mono":
            return {"decision": "rebalance-mono", "gains_db": g,
                    "reason": f"squilibrio {diff:+.1f} dB su segnali diversi (correlazione {xc:.2f}): "
                              f"canali riallineati con pan ({g}) e sommati in mono (--balance mono)"}
        return {"decision": "rebalance", "gains_db": g,
                "reason": f"squilibrio {diff:+.1f} dB su segnali diversi (correlazione {xc:.2f}, nessun "
                          f"pattern a due microfoni): ribilanciamento con pan {g}, stereo conservato"}
    if mode == "mono":
        return {"decision": "average", "reason": f"canali bilanciati (Δ {diff:+.1f} dB): somma mono (--balance mono)"}
    return {"decision": "keep", "reason": f"canali bilanciati (Δ {diff:+.1f} dB ≤ {IMBALANCE_DB:.0f} dB): nessun intervento"}


def _automix_gains(m: dict) -> dict:
    """Guadagni per allineare i due microfoni sul loro livello di parlato dominante."""
    lv = m.get("dominant_level_db", {})
    if lv.get("L") is None or lv.get("R") is None:
        return {"L": 0.0, "R": 0.0}
    mid = (lv["L"] + lv["R"]) / 2
    clamp = lambda x: max(-12.0, min(12.0, x))  # noqa: E731
    return {"L": round(clamp(mid - lv["L"]), 2), "R": round(clamp(mid - lv["R"]), 2)}


def _pan_filter(decision: dict) -> list[str]:
    """Filtro pan ffmpeg per le decisioni che non richiedono l'automix."""
    d = decision["decision"]
    g = decision.get("gains_db") or {}
    gl, gr = (10 ** (g.get("L", 0) / 20), 10 ** (g.get("R", 0) / 20))
    return {
        "keep": [],
        "mono-input": ["pan=stereo|c0=c0|c1=c0"],
        "left": ["pan=stereo|c0=c0|c1=c0"],
        "right": ["pan=stereo|c0=c1|c1=c1"],
        "average": ["pan=stereo|c0=0.5*c0+0.5*c1|c1=0.5*c0+0.5*c1"],
        "rebalance": [f"pan=stereo|c0={gl:.5f}*c0|c1={gr:.5f}*c1"],
        "rebalance-mono": [f"pan=stereo|c0={gl / 2:.5f}*c0+{gr / 2:.5f}*c1|c1={gl / 2:.5f}*c0+{gr / 2:.5f}*c1"],
        "automix": ["pan=stereo|c0=c0|c1=c0"],  # applicato al WAV mono dell'automix
    }[d]


def automix_to_wav(path: Path | str, info: dict, metrics: dict, gains_db: dict, out_wav: Path,
                   attack_ms: float = 10.0, release_ms: float = 250.0) -> dict:
    """Automix a gain-sharing (Dugan): ogni microfono pesa per la sua quota di potenza
    (inviluppo 10 ms, attacco rapido, rilascio lento). Scrive WAV mono float 48 kHz."""
    import soundfile as sf

    t0 = time.time()
    fine = metrics["_fine"]
    gl, gr = 10 ** (gains_db.get("L", 0) / 10), 10 ** (gains_db.get("R", 0) / 10)
    pL = np.asarray(fine["eL"], dtype=np.float64) * gl
    pR = np.asarray(fine["eR"], dtype=np.float64) * gr
    a_att = math.exp(-FINE_SEC / (attack_ms / 1000))
    a_rel = math.exp(-FINE_SEC / (release_ms / 1000))

    def follow(p: np.ndarray) -> np.ndarray:  # inseguitore di inviluppo (potenza)
        out = np.empty_like(p)
        s = float(p[0]) if len(p) else 0.0
        for i, x in enumerate(p.tolist()):
            a = a_att if x > s else a_rel
            s = a * s + (1 - a) * x
            out[i] = s
        return out

    sL, sR = follow(pL), follow(pR)
    eps = 1e-10
    w = sL / (sL + sR + eps)
    w[(sL + sR) < eps] = 0.5
    centers = (np.arange(len(w)) + 0.5) * FINE_SEC * SR_OUT   # centri blocchi in campioni 48k
    ampL, ampR = 10 ** (gains_db.get("L", 0) / 20), 10 ** (gains_db.get("R", 0) / 20)

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    pos = 0
    peak = 0.0
    with sf.SoundFile(str(out_wav), "w", samplerate=SR_OUT, channels=1, subtype="FLOAT") as fh:
        for block in _decode_chunks(path, info, SR_OUT, 2, int(SR_OUT * CHUNK_SEC)):
            n = len(block)
            idx = np.arange(pos, pos + n, dtype=np.float64)
            wl = np.interp(idx, centers, w) if len(w) else np.full(n, 0.5)
            y = wl * ampL * block[:, 0] + (1 - wl) * ampR * block[:, 1]
            peak = max(peak, float(np.abs(y).max()) if n else 0.0)
            fh.write(y.astype(np.float32))
            pos += n
    share_L = float(np.mean(w)) if len(w) else 0.5
    return {"samples": pos, "duration": round(pos / SR_OUT, 3), "mean_weight_L": round(share_L, 3),
            "attack_ms": attack_ms, "release_ms": release_ms, "sample_peak_db": round(20 * math.log10(peak + 1e-12), 2),
            "elapsed_s": round(time.time() - t0, 2)}


def balance_stage(path: Path | str, mode: str, tmpdir: Path, info: dict | None = None) -> tuple[Path, dict, list[str], dict]:
    """Prepara l'ingresso per ffmpeg: ritorna (file, info, filtri_pan, report_bilanciamento)."""
    info = info or probe_audio(path)
    if mode == "none":
        return Path(path), info, [], {"mode": mode, "decision": "keep", "reason": "--balance none"}
    metrics = analyze_balance(path, info)
    decision = decide_balance(metrics, mode)
    report = {"mode": mode, **{k: v for k, v in metrics.items() if not k.startswith("_")}, **decision}
    if decision["decision"] == "automix":
        wav = tmpdir / "automix.wav"
        report["automix"] = automix_to_wav(path, info, metrics, decision.get("gains_db", {}), wav)
        return wav, probe_audio(wav), _pan_filter(decision), report
    return Path(path), info, _pan_filter(decision), report


# ── Misure ──────────────────────────────────────────────────────────────────
def _last_json_block(text: str) -> dict:
    m = re.findall(r"\{[^{}]*\}", text, re.S)
    if not m:
        raise RuntimeError("loudnorm: JSON di misura non trovato nell'output di ffmpeg")
    return json.loads(m[-1])


def measure_ebur128(path: Path | str, info: dict | None = None, prefilter: list[str] | None = None) -> dict:
    """Misura EBU R128 (I, LRA, true peak) con il filtro ebur128 di ffmpeg."""
    info = info or probe_audio(path)
    chain = [ASYNC, *(prefilter or []), "ebur128=peak=true:framelog=verbose"]
    proc = yc.run([yc.FFMPEG, "-hide_banner", "-nostdin", "-v", "info", *_ff_input(path, info),
                   "-map", "0:a:0", "-vn", "-af", ",".join(chain), "-f", "null", "-"], capture=True)
    txt = proc.stderr
    summary = txt[txt.rfind("Summary:"):] if "Summary:" in txt else txt

    def grab(pat: str) -> float | None:
        mm = re.search(pat, summary, re.S)
        return float(mm.group(1)) if mm else None

    return {"I": grab(r"I:\s+(-?[\d.]+|-inf) LUFS"), "LRA": grab(r"LRA:\s+(-?[\d.]+) LU"),
            "threshold": grab(r"Integrated loudness:.*?Threshold:\s+(-?[\d.]+) LUFS"),
            "TP": grab(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS")}


def _loudnorm_pass1(path: Path, info: dict, pre: list[str], I: float, TP: float, LRA: float) -> dict:
    """Passo 1. Misura con ebur128 (≈6× più veloce del loudnorm in analisi, che lavora a
    192 kHz): in modalità lineare loudnorm usa solo measured_*. Se la modalità lineare è
    impossibile (LRA sorgente > target) serve il vero passo 1 di loudnorm per `target_offset`."""
    m = measure_ebur128(path, info, pre)
    if None not in (m["I"], m["TP"], m["LRA"], m["threshold"]) and m["LRA"] <= LRA and math.isfinite(m["I"]):
        return {"input_i": m["I"], "input_tp": m["TP"], "input_lra": m["LRA"], "input_thresh": m["threshold"],
                "target_offset": 0.0, "method": "ebur128"}
    af = ",".join([ASYNC, *pre, f"loudnorm=I={I}:TP={TP}:LRA={LRA}:print_format=json"])
    proc = yc.run([yc.FFMPEG, "-hide_banner", "-nostdin", "-v", "info", *_ff_input(path, info),
                   "-map", "0:a:0", "-vn", "-af", af, "-f", "null", "-"], capture=True)
    return {**_last_json_block(proc.stderr), "method": "loudnorm"}


def _encode_args(out: Path, channels: int) -> list[str]:
    ext = out.suffix.lower()
    common = ["-ar", str(SR_OUT), "-ac", str(channels)]
    if ext == ".wav":
        return [*common, "-c:a", "pcm_s24le"]
    if ext == ".flac":
        return [*common, "-c:a", "flac"]
    if ext in (".m4a", ".mp4", ".aac", ".mov"):
        enc = ["-c:a", "aac_at", "-aac_at_mode", "cbr", "-b:a", "320k"]
        return [*common, *enc, *(["-movflags", "+faststart"] if ext in (".m4a", ".mp4") else [])]
    raise ValueError(f"Formato di uscita non supportato: {ext} (usa .wav, .flac, .m4a)")


# ── Normalizzazione completa ────────────────────────────────────────────────
def normalize(inp: Path | str, out: Path | str, *, target: float = -14.0, tp: float = -1.5, lra: float = 11.0,
              balance: str = "auto", chain: str = "none", channels: int = 2, report_path: Path | None = None,
              force: bool = False, tolerance: float = 0.5) -> dict:
    """Bilanciamento + loudnorm a due passaggi + verifica. Ritorna il report (dict)."""
    inp, out = Path(inp).expanduser().resolve(), Path(out).expanduser().resolve()
    if inp == out:
        raise ValueError("IN e OUT coincidono: non si sovrascrive mai l'originale")
    if not inp.exists():
        raise FileNotFoundError(f"File di ingresso non trovato: {inp}")
    report_path = Path(report_path) if report_path else out.with_suffix(".loudnorm.json")
    params = {"target_I": target, "target_TP": tp, "target_LRA": lra, "balance": balance,
              "chain": chain, "channels": channels, "version": REPORT_VERSION}

    if (not force and out.exists() and report_path.exists()
            and out.stat().st_mtime >= inp.stat().st_mtime):
        try:
            old = yc.read_json(report_path)
            if old.get("params") == params and old.get("verified"):
                yc.log(f"✓ {out.name} già normalizzato (usa --force per rifare)")
                return {**old, "skipped": True}
        except Exception:  # report illeggibile → si rifà
            pass

    timings: dict[str, float] = {}
    t_all = time.time()
    info = probe_audio(inp)
    yc.log(f"▶ {inp.name}: {info['codec']} {info['channels']}ch {info['sample_rate']} Hz, {info['duration']:.1f} s")

    out.parent.mkdir(parents=True, exist_ok=True)
    tmpdir = Path(tempfile.mkdtemp(prefix=".loudnorm-", dir=out.parent))
    try:
        # misura "prima" e analisi/automix dei canali in parallelo (due decodifiche indipendenti)
        t = time.time()
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_before = ex.submit(measure_ebur128, inp, info)
            src, src_info, pre, bal = balance_stage(inp, balance, tmpdir, info)
            before = f_before.result()
        timings["measure_before+balance"] = round(time.time() - t, 2)
        yc.log(f"  prima: I {before['I']} LUFS · LRA {before['LRA']} LU · TP {before['TP']} dBTP")
        yc.log(f"  bilanciamento: {bal['decision']} — {bal.get('reason', '')}")
        if chain == "gentle":
            pre = [*pre, *GENTLE_CHAIN]

        # passo 1: misura sull'audio già bilanciato (e catena)
        t = time.time()
        m1 = _loudnorm_pass1(src, src_info, pre, target, tp, lra)
        timings["pass1"] = round(time.time() - t, 2)
        gain = target - float(m1["input_i"])
        predicted_tp = float(m1["input_tp"]) + gain
        limiter = None
        if predicted_tp > tp:
            # il guadagno lineare porterebbe il picco oltre il tetto: limitatore prima (con
            # compensazione della latenza) così il passo 2 resta lineare
            # limite in dBFS (picco campione) con 1 dB di margine per i picchi inter-campione
            limit_db = min(tp - gain - 1.0, -0.5)
            lin = max(0.0625, 10 ** (limit_db / 20))
            limiter = {"limit_dbfs": round(20 * math.log10(lin), 2), "reason": f"TP previsto {predicted_tp:+.1f} dBTP"}
            pre = [*pre, f"alimiter=limit={lin:.5f}:level=0:attack=5:release=50:latency=1"]
            t = time.time()
            m1 = _loudnorm_pass1(src, src_info, pre, target, tp, lra)
            timings["pass1_limited"] = round(time.time() - t, 2)

        # passo 2. Se la modalità lineare è possibile (LRA ≤ target, picco previsto ≤ tetto) è un
        # guadagno costante: lo applichiamo con `volume` (identico a loudnorm linear=true, che però
        # ricampiona tutto a 192 kHz ed è ~10× più lento). Altrimenti loudnorm (che passa in dinamico).
        gain = target - float(m1["input_i"])
        predicted_tp = float(m1["input_tp"]) + gain
        post = ["pan=mono|c0=0.5*c0+0.5*c1"] if channels == 1 and src_info["channels"] >= 2 else []
        linear_ok = m1.get("method") == "ebur128" and predicted_tp <= tp + 0.05
        if linear_ok:
            norm = [f"volume={gain:.3f}dB"]
        else:
            norm = [f"loudnorm=I={target}:TP={tp}:LRA={lra}:measured_I={m1['input_i']}:measured_TP={m1['input_tp']}"
                    f":measured_LRA={m1['input_lra']}:measured_thresh={m1['input_thresh']}"
                    f":offset={m1['target_offset']}:linear=true:print_format=json"]
        af = ",".join([ASYNC, *pre, *norm, f"aresample={SR_OUT}", *post])
        tmp_out = tmpdir / f"out{out.suffix}"
        t = time.time()
        proc = yc.run([yc.FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "info", *_ff_input(src, src_info),
                       "-map", "0:a:0", "-vn", "-af", af, *_encode_args(out, channels), str(tmp_out)], capture=True)
        timings["pass2"] = round(time.time() - t, 2)
        if linear_ok:
            m2 = {"normalization_type": "linear", "engine": "volume (= loudnorm linear)", "gain_db": round(gain, 3),
                  "predicted_tp": round(predicted_tp, 2)}
        else:
            m2 = {**_last_json_block(proc.stderr), "engine": "loudnorm"}

        # verifica (ebur128 sul file scritto) + eventuale correzione di guadagno
        t = time.time()
        out_info = probe_audio(tmp_out)
        after = measure_ebur128(tmp_out, out_info)
        correction = None
        if after["I"] is not None and abs(after["I"] - target) > 0.2:
            delta = target - after["I"]
            if after["TP"] is None or after["TP"] + delta <= tp + 0.1:
                fixed = tmpdir / f"fixed{out.suffix}"
                yc.run([yc.FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "error", *_ff_input(tmp_out, out_info),
                        "-map", "0:a:0", "-af", f"{ASYNC},volume={delta:.3f}dB", *_encode_args(out, channels), str(fixed)])
                fixed.replace(tmp_out)
                correction = {"gain_db": round(delta, 3)}
                after = measure_ebur128(tmp_out, out_info)
        timings["verify"] = round(time.time() - t, 2)

        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_out), str(out))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    delta_lu = None if after["I"] is None else round(after["I"] - target, 2)
    verified = (delta_lu is not None and abs(delta_lu) <= tolerance
                and (after["TP"] is None or after["TP"] <= tp + 0.5))
    in_dur, out_dur = info["duration"], probe_audio(out)["duration"]
    report = {
        "input": str(inp), "output": str(out), "params": params,
        "input_info": info, "before": before, "balance": bal,
        "chain": GENTLE_CHAIN if chain == "gentle" else [],
        "limiter": limiter,
        "pass1": {k: m1.get(k) for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset", "method")},
        "pass2": {k: m2.get(k) for k in ("normalization_type", "engine", "gain_db", "predicted_tp", "output_i",
                                         "output_tp", "output_lra", "target_offset") if m2.get(k) is not None},
        "correction": correction, "after": after, "delta_lu": delta_lu, "verified": verified,
        "duration": {"input": round(in_dur, 3), "output": round(out_dur, 3), "delta_ms": round((out_dur - in_dur) * 1000, 1)},
        "timings": {**timings, "total": round(time.time() - t_all, 2)},
    }
    yc.write_json(report_path, report)
    yc.log(f"  dopo:  I {after['I']} LUFS · LRA {after['LRA']} LU · TP {after['TP']} dBTP "
           f"({m2.get('normalization_type')}) → {'OK' if verified else 'FUORI TOLLERANZA'}")
    return {**report, "report": str(report_path)}


def render_balanced(inp: Path | str, out_wav: Path, mode: str, tmpdir: Path) -> dict:
    """Solo bilanciamento (niente loudness): WAV stereo float32 48 kHz (float: i picchi > 0 dBFS
    del dialogo non ancora normalizzato restano intatti). Usato da yt-edl-render."""
    src, src_info, pre, bal = balance_stage(inp, mode, tmpdir)
    af = ",".join([ASYNC, *pre, f"aresample={SR_OUT}"])
    yc.run([yc.FFMPEG, "-hide_banner", "-nostdin", "-y", "-v", "error", *_ff_input(src, src_info),
            "-map", "0:a:0", "-vn", "-af", af, "-ac", "2", "-c:a", "pcm_f32le", str(out_wav)])
    return bal


# ── CLI ─────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(
        prog="yt-loudnorm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Normalizza la loudness (EBU R128, due passaggi, lineare quando possibile) "
                    "e sistema lo squilibrio L/R. IN può essere audio o video (prima traccia audio).",
        epilog="""Esempi:
  yt-loudnorm edit/assembled.mov edit/mix.wav                 # -14 LUFS, -1.5 dBTP, LRA 11, balance auto
  yt-loudnorm master.mp4 mix.m4a --balance mono --chain gentle
  yt-loudnorm master.mp4 /dev/null --analyze                  # solo misure e diagnosi canali

Uscita: WAV 24 bit (default per .wav), FLAC, o AAC 320k (.m4a). 48 kHz, stereo (dual-mono se
il bilanciamento produce mono; --channels 1 per mono vero). Report JSON accanto all'uscita
(<OUT>.loudnorm.json) con misure prima/dopo (ebur128), scelta sui canali e motivazione.
Verifica: |I - target| ≤ 0.5 LU e TP ≤ tetto (+0.5 di tolleranza per l'encoder).""")
    ap.add_argument("inp", metavar="IN", help="file audio o video di ingresso (mai modificato)")
    ap.add_argument("out", metavar="OUT", help="file di uscita (.wav / .flac / .m4a)")
    ap.add_argument("--target", type=float, default=-14.0, help="loudness integrata in LUFS (default -14)")
    ap.add_argument("--tp", type=float, default=-1.5, help="tetto true peak in dBTP (default -1.5)")
    ap.add_argument("--lra", type=float, default=11.0, help="loudness range massimo in LU (default 11)")
    ap.add_argument("--balance", choices=BALANCE_MODES, default="auto",
                    help="gestione canali L/R: auto (diagnosi e scelta), mono (parlato), none, "
                         "o forzature automix|left|right|average|rebalance (default auto)")
    ap.add_argument("--chain", choices=("none", "gentle"), default="none",
                    help="gentle = highpass 80 Hz + compressione leggera 2:1 a -18 dBFS (default none: "
                         "un master già compresso in registrazione non ne ha bisogno)")
    ap.add_argument("--channels", type=int, choices=(1, 2), default=2, help="canali in uscita (default 2)")
    ap.add_argument("--report", help="percorso del report JSON (default <OUT>.loudnorm.json)")
    ap.add_argument("--analyze", action="store_true", help="solo analisi (loudness + canali), nessun file scritto")
    ap.add_argument("--force", action="store_true", help="rifà anche se l'uscita è aggiornata")
    a = ap.parse_args()

    try:
        if a.analyze:
            inp = Path(a.inp).expanduser().resolve()
            info = probe_audio(inp)
            before = measure_ebur128(inp, info)
            metrics = analyze_balance(inp, info) if info["channels"] >= 2 else {"channels": info["channels"]}
            decision = decide_balance(metrics, a.balance)
            yc.emit(True, input=str(inp), input_info=info, loudness=before,
                    balance={**{k: v for k, v in metrics.items() if not k.startswith("_")}, **decision},
                    gain_to_target_db=None if before["I"] is None else round(a.target - before["I"], 2),
                    outputs={}, warnings=[])
            return
        rep = normalize(a.inp, a.out, target=a.target, tp=a.tp, lra=a.lra, balance=a.balance, chain=a.chain,
                        channels=a.channels, report_path=Path(a.report) if a.report else None, force=a.force)
    except Exception as exc:  # noqa: BLE001
        yc.fail(str(exc))
        return
    warnings = []
    if not rep.get("verified"):
        warnings.append(f"Loudness fuori tolleranza: I {rep['after']['I']} LUFS (target {a.target}), TP {rep['after']['TP']}")
    if rep["pass2"].get("normalization_type") == "dynamic":
        warnings.append("loudnorm è passato in modalità dinamica (LRA sorgente > target o picchi): "
                        "alza --lra o usa --chain gentle se vuoi la modalità lineare")
    if abs(rep["duration"]["delta_ms"]) > 50:
        warnings.append(f"Durata uscita diversa dall'ingresso di {rep['duration']['delta_ms']} ms")
    yc.emit(rep.get("verified", False) or bool(rep.get("skipped")),
            outputs={"audio": rep["output"], "report": rep.get("report", str(Path(rep["output"]).with_suffix('.loudnorm.json')))},
            skipped=bool(rep.get("skipped")),
            before=rep["before"], after=rep["after"], delta_lu=rep["delta_lu"],
            balance={k: rep["balance"].get(k) for k in ("decision", "reason", "diff_db", "diff_active_db",
                                                         "dominance", "xcorr", "gains_db") if k in rep["balance"]},
            normalization_type=rep["pass2"].get("normalization_type"), limiter=rep.get("limiter"),
            timings=rep["timings"], warnings=warnings)


if __name__ == "__main__":
    main()

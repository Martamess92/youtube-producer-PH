"""yt-ingest — analisi iniziale del sorgente: inventario, integrità, audio, loudness, proxy, frame.

Uso:
  yt-ingest WORKDIR                      # tutto, proxy 720p solo se il sorgente è >1080p
  yt-ingest WORKDIR --no-proxy           # integrità + audio + frame, senza proxy
  yt-ingest WORKDIR --frames-every 10    # campione frame più fitto (0 = nessun frame)
  yt-ingest WORKDIR --no-integrity       # salta la decodifica completa (niente corrupt_spans)

Cosa produce (in <workdir>/analysis/):
  inventory.json   ffprobe, corrupt_spans (errori di decodifica con timestamp), errori AAC
                   nativo vs aac_at con i tempi degli errori nativi e la DECISIONE sul decoder
                   (audio_decode.decision, anche in project.json audio_decoder), loudness EBU R128
                   (I, LRA, true peak), RMS/picco per canale, lr_balance_db (= L − R in dB)
  audio16k.wav     mono 16 kHz PCM s16 (per ASR e diarizzazione)
  audio48k.wav     stereo 48 kHz PCM float32 (per il mix; float = niente clipping: i picchi > 0 dBFS
                   del master restano, se decodificato col decoder nativo)
  proxy.mp4        720p H.264 VideoToolbox + AAC, stesso timeline del sorgente
  frames/          t_<secondi>.jpg ogni N s (960 px di larghezza) + index.json
  contact.jpg      contact sheet dei frame con timecode

Sorgenti secondari (--source B, camere/mic): stessi output in analysis/source-<KEY>/.

Decoder AAC (policy in ytcore.aac_decoder_policy): la passata audio usa il decoder nativo di
FFmpeg (float, nessun clipping) e intanto data ogni suo errore; una seconda passata conta gli
errori di aac_at (AudioToolbox, sempre s16: picchi > 0 dBFS tagliati). Finita l'integrità video:
  nativo  se non ha errori o se TUTTI cadono entro ±3 s da uno span corrotto (caso tipico: una
          raffica di errori a ridosso di un tratto di video rovinato; il buco diventa silenzio con
          aresample async e il timeline resta quello del contenitore);
  aac_at  altrimenti, oppure se ci sono errori nativi e l'integrità non è stata verificata.
La decisione (con il motivo) va in inventory.json audio_decode e in project.json audio_decoder
(+ audio_decoder_by_source); tutti gli altri comandi la leggono da lì. Se la decisione è aac_at,
la passata audio si rifà con aac_at. YT_AAC_DECODER=native|aac_at forza il decoder dei WAV.
WAV già presenti ma fatti con un altro decoder: rigenerati se non c'è ancora un transcript,
altrimenti solo un avviso (serve --force, e poi yt-transcribe).

Prestazioni: integrità, proxy e frame condividono UNA sola decodifica VideoToolbox (frame
tenuti in GPU, scale_vt); le passate audio girano in parallelo alla passata video.
Idempotente: rifà solo i passi con output mancanti o più vecchi del sorgente (--force per tutto).
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import re
import shutil
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path

import ytcore
from frames import (JPEG_TAIL, SAMPLER_VERSION, contact_sheet, extract_at_times, fps_sampler, frame_name,
                    probe_summary, sw_download_format, vt_ok)
from ytcore import FFMPEG, emit, fail, fmt_ts, log

STATUS_ORDER = ["new", "ingested", "transcribed", "story", "edit", "delivered"]
RE_SHOWINFO = re.compile(r"n:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:\s*(-?[\d.]+(?:e-?\d+)?)")
RE_LEVEL = re.compile(r"\[(fatal|error|warning)\]")
RE_ADDR = re.compile(r"0x[0-9a-f]+")
VIDEO_CTX = ("[hevc", "[h264", "[prores", "[vp9", "[av1", "[mpeg", "vist#", "dec:hevc", "dec:h264")
AUDIO_CTX = ("[aac", "aist#", "dec:aac", "[mp3", "[opus", "[pcm")


# ── Utilità ─────────────────────────────────────────────────────────────────
def _fresh(paths: list[Path], src: Path) -> bool:
    """True se tutti gli output esistono, non sono vuoti e sono più recenti del sorgente."""
    try:
        m = src.stat().st_mtime
        return all(p.exists() and p.stat().st_size > 0 and p.stat().st_mtime >= m for p in paths)
    except OSError:
        return False


def _norm_msg(line: str) -> str:
    """Messaggio di errore senza prefisso/indirizzi/numeri, per raggruppare."""
    msg = line.split("] ", 1)[-1] if "] " in line else line
    msg = RE_LEVEL.sub("", msg)
    msg = RE_ADDR.sub("", msg)
    msg = re.sub(r"\[[^\]]*\]\s*", "", msg)
    msg = re.sub(r"-?\d+", "N", msg)
    return msg.strip()[:120]


def _ctx(line: str) -> str:
    head = line[:80].lower()
    if any(c in head for c in AUDIO_CTX):
        return "audio"
    if any(c in head for c in VIDEO_CTX):
        return "video"
    return "other"


def _is_cli_line(line: str) -> bool:
    """Righe del livello CLI di ffmpeg (vist#/aist#) che ripetono l'errore del decoder."""
    return "vist#" in line[:40] or "aist#" in line[:40]


def cluster(events: list[dict], merge_gap: float) -> list[dict]:
    """Unisce eventi (errori e buchi di frame) più vicini di merge_gap secondi in span.

    Gli errori del decoder arrivano con il pts dell'ultimo frame filtrato: il decoder lavora
    in anticipo di qualche frame (thread), quindi il punto reale è in [t, t + lag]. I buchi
    (frame mancanti) sono invece esatti: se uno span ne contiene, i suoi estremi sono i buchi.
    """
    out: list[dict] = []
    for ev in sorted(events, key=lambda e: e["start"]):
        if out and ev["start"] - out[-1]["_end"] <= merge_gap:
            out[-1]["_ev"].append(ev)
            out[-1]["_end"] = max(out[-1]["_end"], ev["end"])
        else:
            out.append({"_ev": [ev], "_end": ev["end"]})
    spans = []
    for c in out:
        evs = c["_ev"]
        gaps = [e for e in evs if e["kind"] == "gap"]
        errs = [e for e in evs if e["kind"] == "error"]
        if gaps:
            start, end = min(g["start"] for g in gaps), max(g["end"] for g in gaps)
        else:
            start, end = min(e["start"] for e in errs), max(e["end"] for e in errs)
        own = [e for e in errs if e.get("count", 1)] or errs
        msgs = Counter(e["msg"] for e in own)
        spans.append({
            "start": round(start, 3),
            "end": round(end, 3),
            "errors": sum(e.get("count", 1) for e in errs),
            "frames_missing": sum(g.get("missing", 0) for g in gaps),
            "first_error_at": round(min(e["start"] for e in errs), 3) if errs else None,
            "kind": "decode_error" if errs else "missing_frames",
            "messages": [m for m, _ in msgs.most_common(3)],
            "label": f"{fmt_ts(start)}–{fmt_ts(end)}",
        })
    return spans


# ── Passata audio (decoder della policy): wav + loudness + astats ───────────
def _channel_names(n: int, layout: str | None) -> list[str]:
    if n == 2:
        return ["L", "R"]
    if n == 1:
        return ["M"]
    return [f"c{i}" for i in range(n)]


def _decoder_name(codec: str, decoder: str) -> str:
    """Nome del decoder effettivo: 'native' | 'aac_at' per AAC, altrimenti il codec."""
    return (decoder if decoder in ytcore.AAC_DECODERS else "native") if codec == "aac" else codec


def audio_pass(src: Path, summary: dict, analysis: Path, logfile: Path, decoder: str = "native") -> dict:
    a = summary["audio"]
    ch = a["channels"]
    dec = _decoder_name(a["codec"], decoder)
    to_stereo = {1: "pan=stereo|c0=c0|c1=c0,", 2: ""}.get(ch, "aformat=channel_layouts=stereo,")
    to_mono = {1: "", 2: "pan=mono|c0=0.5*c0+0.5*c1,"}.get(ch, "aformat=channel_layouts=mono,")
    graph = (
        # async: riempie di silenzio i buchi di timestamp (pacchetti AAC mancanti o corti), così i WAV
        # restano sul timeline del contenitore e trascrizione/tagli non slittano dopo un buco
        "[0:a:0]ashowinfo,aresample=async=1:min_hard_comp=0.02:first_pts=0,asplit=4[a48][a16][alu][ast];"
        f"[a48]{to_stereo}aresample=48000:resampler=soxr:precision=28[o48];"
        f"[a16]{to_mono}aresample=16000:resampler=soxr[o16];"
        "[alu]ebur128=peak=sample+true:framelog=quiet,anullsink;"
        "[ast]astats=measure_overall=RMS_level+Peak_level:measure_perchannel=RMS_level+Peak_level+DC_offset,anullsink"
    )
    a48, a16 = analysis / "audio48k.wav", analysis / "audio16k.wav"
    t48, t16 = analysis / ".audio48k.part.wav", analysis / ".audio16k.part.wav"
    cmd = [FFMPEG, "-nostdin", "-hide_banner", "-nostats", "-y", "-loglevel", "level+info"]
    if a["codec"] == "aac":
        cmd += ytcore.aac_decoder_input_args(dec)
    cmd += ["-i", str(src), "-vn", "-sn", "-dn", "-filter_complex", graph,
            "-map", "[o48]", "-c:a", "pcm_f32le", "-rf64", "auto", str(t48),
            "-map", "[o16]", "-c:a", "pcm_s16le", str(t16)]
    t0 = time.time()
    res = _run_audio(cmd, logfile, f"audio ({dec})")
    if res["returncode"] != 0:
        raise RuntimeError(f"passata audio fallita (exit {res['returncode']}): {res['tail']}")
    t48.replace(a48)
    t16.replace(a16)
    names = _channel_names(ch, a.get("layout"))
    loud = res["ebur128"]
    chans = []
    for i, st in enumerate(res["astats"]["channels"]):
        chans.append({"ch": names[i] if i < len(names) else f"c{i}", **st})
    balance = None
    if len(chans) == 2 and chans[0].get("rms_db") is not None and chans[1].get("rms_db") is not None:
        balance = round(chans[0]["rms_db"] - chans[1]["rms_db"], 2)
    return {
        "decoder": dec,
        "decoder_errors": res["errors"],
        "decoder_error_spans": res["spans"],
        "decoder_error_times": res["times"],
        "sample_peak_dbfs": res["astats"]["overall"].get("peak_db"),
        "wav_duration_s": round(_wav_duration(a48), 4),
        "loudness": {
            "integrated_lufs": loud.get("I"),
            "lra_lu": loud.get("LRA"),
            "true_peak_dbtp": loud.get("true_peak"),
            "sample_peak_dbfs": loud.get("sample_peak"),
            "threshold_lufs": loud.get("threshold"),
            "rms_overall_db": res["astats"]["overall"].get("rms_db"),
            "channels": chans,
            "measured_on": f"{dec} decode",
        },
        "lr_balance_db": balance,
        "elapsed_s": round(time.time() - t0, 1),
    }


def balance_profile(wav: Path, window: float = 30.0, floor_db: float = -50.0) -> dict | None:
    """Bilanciamento L/R per finestre di `window` s (solo finestre con segnale).

    Su un master con due microfoni lo sbilanciamento spesso NON è costante (es. −11.5 dB in un tratto,
    −4 dB dieci minuti dopo): il valore globale da solo non basta per decidere pan vs mono-fold.
    """
    import numpy as np
    import soundfile as sf

    info = sf.info(str(wav))
    if info.channels != 2:
        return None
    sr = info.samplerate
    rows = []
    for i, block in enumerate(sf.blocks(str(wav), blocksize=int(window * sr), dtype="float32", always_2d=True)):
        if len(block) < sr:
            continue
        rms = np.sqrt(np.mean(np.square(block, dtype=np.float64), axis=0))
        db = 20 * np.log10(np.maximum(rms, 1e-10))
        if db.max() < floor_db:
            continue
        rows.append({"t": round(i * window, 1), "l_db": round(float(db[0]), 2), "r_db": round(float(db[1]), 2),
                     "diff_db": round(float(db[0] - db[1]), 2)})
    if not rows:
        return None
    d = np.array([r["diff_db"] for r in rows])
    return {"window_s": window, "median_db": round(float(np.median(d)), 2),
            "p10_db": round(float(np.percentile(d, 10)), 2), "p90_db": round(float(np.percentile(d, 90)), 2),
            "min_db": round(float(d.min()), 2), "max_db": round(float(d.max()), 2), "windows": rows}


def _wav_duration(path: Path) -> float:
    import soundfile as sf

    info = sf.info(str(path))
    return info.frames / info.samplerate


def decoder_check(src: Path, decoder: str, logfile: Path) -> dict:
    """Decodifica AAC con `decoder` ('native' = aac di FFmpeg, 'aac_at') solo per contare e datare
    gli errori e misurare il picco campione (niente WAV)."""
    cmd = [FFMPEG, "-nostdin", "-hide_banner", "-nostats", "-loglevel", "level+info",
           "-c:a", "aac_at" if decoder == "aac_at" else "aac",
           "-i", str(src), "-vn", "-sn", "-dn", "-map", "0:a:0",
           "-af", "ashowinfo,astats=measure_overall=Peak_level:measure_perchannel=none", "-f", "null", "-"]
    t0 = time.time()
    res = _run_audio(cmd, logfile, f"controllo decoder AAC {decoder}")
    return {"decoder": decoder, "errors": res["errors"], "error_spans": res["spans"], "error_times": res["times"],
            "sample_peak_dbfs": res["astats"]["overall"].get("peak_db"),
            "returncode": res["returncode"], "elapsed_s": round(time.time() - t0, 1)}


def _audio_decode_fields(main_a: dict, summary: dict) -> dict:
    """Campi di inventory.audio_decode dalla passata che ha scritto i WAV (+ evidenze del suo decoder)."""
    cont = summary["audio"].get("duration") or summary.get("duration")
    out = {"decoder": main_a["decoder"], "decoder_errors": main_a["decoder_errors"],
           "decoder_error_spans": main_a["decoder_error_spans"], "wav_duration_s": main_a.get("wav_duration_s"),
           "container_audio_duration_s": round(cont, 4) if cont else None}
    if out["wav_duration_s"] is not None and cont:
        out["wav_delta_ms"] = round((out["wav_duration_s"] - cont) * 1000, 1)
    if main_a["decoder"] in ytcore.AAC_DECODERS:
        out.update(_check_fields({"decoder": main_a["decoder"], "errors": main_a["decoder_errors"],
                                  "error_spans": main_a["decoder_error_spans"],
                                  "error_times": main_a["decoder_error_times"],
                                  "sample_peak_dbfs": main_a.get("sample_peak_dbfs")}))
    return out


def _check_fields(res: dict) -> dict:
    """Evidenze di un decoder AAC → campi native_aac_* o aac_at_* di inventory.audio_decode."""
    if res["decoder"] == "native":
        return {"native_aac_errors": res["errors"], "native_aac_error_spans": res["error_spans"],
                "native_aac_error_times": res["error_times"], "native_sample_peak_dbfs": res.get("sample_peak_dbfs")}
    return {"aac_at_errors": res["errors"], "aac_at_error_spans": res["error_spans"],
            "aac_at_sample_peak_dbfs": res.get("sample_peak_dbfs")}


def _run_audio(cmd: list, logfile: Path, label: str) -> dict:
    """Esegue una passata audio leggendo stderr in streaming: errori datati con ashowinfo,
    riepiloghi di ebur128 e astats."""
    log("$", " ".join(ytcore._q(str(c)) for c in cmd))
    proc = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            text=True, errors="replace", bufsize=1)
    last_t = 0.0
    errors: list[dict] = []
    ebur: dict = {}
    astats = {"channels": [], "overall": {}}
    section = None       # sezione corrente del riepilogo ebur128
    cur = None           # canale corrente di astats
    tail: list[str] = []
    with open(logfile, "a") as lf:
        lf.write(f"\n### {label} — {dt.datetime.now().isoformat(timespec='seconds')}\n$ {' '.join(map(str, cmd))}\n")
        for line in proc.stderr:
            if "pts_time:" in line and "ashowinfo" in line:
                m = re.search(r"pts_time:\s*(-?[\d.]+)", line)
                if m:
                    last_t = float(m.group(1))
                continue
            lf.write(line)
            tail = (tail + [line.rstrip()])[-15:]
            s = line.strip()
            lvl = RE_LEVEL.search(line)
            if lvl and lvl.group(1) in ("error", "fatal") and _ctx(line) in ("audio", "other") \
                    and "Parsed_" not in line and "out#" not in line:
                errors.append({"start": last_t, "end": last_t + 0.1, "kind": "error", "msg": _norm_msg(line),
                               "count": 0 if _is_cli_line(line) else 1})
                continue
            # ebur128: il riepilogo è multi-riga, solo la prima ha il prefisso.
            if "Summary:" in s and "ebur128" in line:
                section = "summary"
                continue
            if section:
                if s.startswith("Integrated loudness"):
                    section = "I"
                elif s.startswith("Loudness range"):
                    section = "LRA"
                elif s.startswith("Sample peak"):
                    section = "sample"
                elif s.startswith("True peak"):
                    section = "true"
                else:
                    m = re.match(r"(I|Threshold|LRA|Peak):\s*(-?[\d.]+|-inf)", s)
                    if m:
                        val = float(m.group(2)) if m.group(2) != "-inf" else None
                        key = {("I", "I"): "I", ("I", "Threshold"): "threshold", ("LRA", "LRA"): "LRA",
                               ("sample", "Peak"): "sample_peak", ("true", "Peak"): "true_peak"}.get((section, m.group(1)))
                        if key:
                            ebur[key] = val
                    elif "] [" in line:
                        section = None
            # astats: "Channel: N" … "Overall".
            if "astats" in line:
                body = s.split("] ")[-1]
                m = re.match(r"Channel:\s*(\d+)", body)
                if m:
                    cur = {}
                    astats["channels"].append(cur)
                    continue
                if body.startswith("Overall"):
                    cur = astats["overall"]
                    continue
                m = re.match(r"(RMS level dB|Peak level dB|DC offset):\s*(-?[\d.]+|-inf|inf|nan)", body)
                if m and cur is not None:
                    try:
                        val = float(m.group(2))
                        val = None if math.isinf(val) or math.isnan(val) else round(val, 2)
                    except ValueError:
                        val = None
                    cur[{"RMS level dB": "rms_db", "Peak level dB": "peak_db", "DC offset": "dc_offset"}[m.group(1)]] = val
    proc.wait()
    spans = cluster(errors, 2.0) if errors else []
    for sp in spans:
        for k in ("frames_missing", "kind"):
            sp.pop(k, None)
    n_err = sum(e["count"] for e in errors)
    # tempi (sul timeline del sorgente) degli errori del decoder: pts dell'ultimo frame uscito
    # prima dell'errore, quindi il pacchetto guasto è subito dopo. Unici, al ms, max 1000.
    times = sorted({round(e["start"], 3) for e in errors if e["count"]})[:1000]
    if n_err:
        log(f"  {label}: {n_err} errori di decodifica")
    return {"returncode": proc.returncode, "errors": n_err, "spans": spans, "times": times, "ebur128": ebur,
            "astats": astats, "tail": "\n".join(tail)}


# ── Passata video unica: integrità + proxy + frame ──────────────────────────
def video_pass(src: Path, summary: dict, analysis: Path, logfile: Path, *, proxy: bool, frames_every: float,
               frame_width: int, proxy_bitrate: str, hw: bool, merge_gap: float,
               proxy_decoder: str = "native") -> dict:
    v = summary["video"]
    fps = v.get("fps") or v.get("avg_fps") or 30.0
    fd = 1.0 / fps
    duration = v.get("duration") or summary["duration"] or 1.0
    branches = []
    graph = []
    outs: list[str] = []
    tmp_frames = None
    proxy_tmp = analysis / ".proxy.part.mp4"
    if proxy:
        branches.append("vp")
    if frames_every > 0:
        branches.append("vf")
    if not proxy:
        branches.append("vn")  # serve un'uscita a piena cadenza per decodificare tutto
    head = "[0:v:0]showinfo=checksum=0"
    graph.append(head + (f",split={len(branches)}" + "".join(f"[{b}]" for b in branches) if len(branches) > 1
                         else f"[{branches[0]}]"))
    landscape = (v["width"] or 0) >= (v["height"] or 0)
    pw, ph = ("-2", "720") if landscape else ("720", "-2")
    swfmt = sw_download_format(v.get("pix_fmt"))
    if proxy:
        graph.append(f"[vp]scale_vt=w={pw}:h={ph}[vprox]" if hw
                     else f"[vp]scale=w={pw}:h={ph}:flags=bicubic,format=yuv420p[vprox]")
        outs += ["-map", "[vprox]"]
        if summary.get("audio"):
            # async: i pacchetti scartati dal decoder (o i buchi di timestamp) diventano silenzio,
            # così l'audio del proxy resta sul timeline del contenitore
            outs += ["-map", "0:a:0", "-af", ytcore.AUDIO_ASYNC, "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
                     "-ac", "2"]
        outs += ["-c:v", "h264_videotoolbox", "-b:v", proxy_bitrate, "-g", str(int(round(fps * 2))),
                 "-profile:v", "high", "-movflags", "+faststart", str(proxy_tmp)]
    if frames_every > 0:
        tmp_frames = analysis / ".frames.part"
        shutil.rmtree(tmp_frames, ignore_errors=True)
        tmp_frames.mkdir(parents=True)
        fw = min(frame_width, v["width"] or frame_width) // 2 * 2
        if hw:
            graph.append(f"[vf]{fps_sampler(frames_every)},scale_vt=w={fw}:h=-2,hwdownload,format={swfmt},{JPEG_TAIL}[vfr]")
        else:
            graph.append(f"[vf]{fps_sampler(frames_every)},scale=w={fw}:h=-2:flags=lanczos,{JPEG_TAIL}[vfr]")
        outs += ["-map", "[vfr]", "-fps_mode", "passthrough", "-q:v", "3", "-start_number", "0",
                 str(tmp_frames / "f_%06d.jpg")]
    if not proxy:
        outs += ["-map", "[vn]", "-f", "null", "-"]
    cmd = [FFMPEG, "-nostdin", "-hide_banner", "-nostats", "-y", "-loglevel", "level+info"]
    if hw:
        cmd += ["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"]
    if proxy and summary.get("audio") and summary["audio"]["codec"] == "aac":
        cmd += ytcore.aac_decoder_input_args(proxy_decoder)
    cmd += ["-i", str(src), "-filter_complex", ";".join(graph), *outs]

    log("$", " ".join(ytcore._q(str(c)) for c in cmd))
    t0 = time.time()
    proc = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                            text=True, errors="replace", bufsize=1)
    gap_thr = 1.5 * fd if not v.get("vfr") else max(1.5 * fd, 0.5)
    lag = 1.0  # anticipo massimo del decoder rispetto al filtro (thread + riordino B-frame)
    last_t = None
    n_frames = 0
    events: list[dict] = []
    audio_errors = 0
    warnings_count = 0
    backwards = 0
    next_report = t0 + 30
    tail: list[str] = []
    with open(logfile, "a") as lf:
        lf.write(f"\n### video — {dt.datetime.now().isoformat(timespec='seconds')}\n$ {' '.join(map(str, cmd))}\n")
        for line in proc.stderr:
            if "showinfo" in line[:60]:
                m = RE_SHOWINFO.search(line)
                if not m:
                    continue  # righe di side data / colore di showinfo
                t = float(m.group(3))
                n_frames += 1
                if last_t is not None:
                    dtt = t - last_t
                    if dtt > gap_thr:
                        missing = max(1, int(round(dtt / fd)) - 1)
                        events.append({"start": last_t + fd, "end": t, "kind": "gap", "missing": missing})
                    elif dtt <= 0:
                        backwards += 1
                last_t = t
                now = time.time()
                if now >= next_report:
                    el = now - t0
                    log(f"  video: {fmt_ts(t, 'yt')} / {fmt_ts(duration, 'yt')} ({100 * t / duration:.0f}%)"
                        f" · {t / el:.1f}× · errori {sum(1 for e in events if e['kind'] == 'error')}"
                        f" · buchi {sum(1 for e in events if e['kind'] == 'gap')}")
                    next_report = now + 30
                continue
            lf.write(line)
            tail = (tail + [line.rstrip()])[-20:]
            lvl = RE_LEVEL.search(line)
            if not lvl:
                continue
            ctx = _ctx(line)
            if ctx == "audio":
                if lvl.group(1) != "warning":
                    audio_errors += 1
                continue
            if ctx != "video":
                continue
            if lvl.group(1) == "warning":
                warnings_count += 1
                continue
            t = last_t if last_t is not None else 0.0
            events.append({"start": t, "end": t + lag, "kind": "error", "msg": _norm_msg(line),
                           "count": 0 if _is_cli_line(line) else 1})
    proc.wait()
    elapsed = time.time() - t0
    # Frame mancanti in coda (dopo l'ultimo frame decodificato).
    if last_t is not None and duration - (last_t + fd) > gap_thr:
        missing = int(round((duration - last_t) / fd)) - 1
        events.append({"start": last_t + fd, "end": duration, "kind": "gap", "missing": missing})
    result = {
        "returncode": proc.returncode,
        "tail": "\n".join(tail),
        "frames_decoded": n_frames,
        "elapsed_s": round(elapsed, 1),
        "speed_x": round(duration / elapsed, 2) if elapsed > 0 else None,
    }
    if proc.returncode != 0 or n_frames == 0:
        proxy_tmp.unlink(missing_ok=True)
        if tmp_frames:
            shutil.rmtree(tmp_frames, ignore_errors=True)
        return result
    expected = v.get("nb_frames") or int(round(duration * fps))
    # Buchi solo nell'ultimo mezzo secondo senza errori: tipico artefatto di un taglio in
    # stream copy (B-frame oltre la fine), non corruzione. Li riportiamo a parte.
    tail_cut = duration - 0.5
    tail = [e for e in events if e["kind"] == "gap" and e["start"] >= tail_cut]
    if tail and not any(e["kind"] == "error" and e["start"] >= tail_cut - merge_gap for e in events):
        events = [e for e in events if e not in tail]
    else:
        tail = []
    errs = [e for e in events if e["kind"] == "error"]
    spans = cluster(events, merge_gap)
    cli_lines = sum(1 for e in errs if not e["count"])
    result["integrity"] = {
        "decoder": f"{v['codec']}+{'videotoolbox' if hw else 'software'}",
        "frames_expected": expected,
        "frames_decoded": n_frames,
        "frames_missing": max(0, expected - n_frames),
        "errors": sum(e["count"] for e in errs),
        "cli_error_lines": cli_lines,
        "decoder_warnings": warnings_count,
        "pts_backwards": backwards,
        "audio_errors_in_pass": audio_errors,
        "merge_gap_s": merge_gap,
        "corrupt_spans": spans,
        "tail_glitches": [{"start": round(e["start"], 3), "end": round(e["end"], 3), "frames_missing": e["missing"]}
                          for e in tail],
        "elapsed_s": round(elapsed, 1),
        "speed_x": result["speed_x"],
        "note": "start/end = frame mancanti (esatti) se presenti, altrimenti [errore, errore+1 s]; "
                "first_error_at anticipa di ~0.3–0.6 s perché il decoder lavora avanti di qualche frame",
    }
    if proxy:
        proxy_tmp.replace(analysis / "proxy.mp4")
        result["proxy"] = str(analysis / "proxy.mp4")
        if summary.get("audio"):
            result["proxy_audio_decoder"] = _decoder_name(summary["audio"]["codec"], proxy_decoder)
    if tmp_frames:
        result["frames"] = _commit_frames(tmp_frames, analysis / "frames", frames_every, duration)
    return result


def _commit_frames(tmp: Path, dest: Path, every: float, duration: float) -> list[dict]:
    """Sposta i frame della passata in frames/ con il nome per tempo (t_<s>.jpg)."""
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("t_*.jpg"):
        old.unlink()
    items = []
    for f in sorted(tmp.glob("f_*.jpg")):
        k = int(f.stem.split("_")[1])
        t = round(k * every, 3)
        if t > duration + 1e-6:
            continue
        name = frame_name(t, "jpg")
        f.replace(dest / name)
        items.append({"t": t, "file": name})
    shutil.rmtree(tmp, ignore_errors=True)
    return items


# ── Flag leggibili ──────────────────────────────────────────────────────────
def build_flags(inv: dict) -> list[str]:
    flags = []
    spans = inv.get("corrupt_spans") or []
    if spans:
        where = ", ".join(s["label"] for s in spans[:8]) + (" …" if len(spans) > 8 else "")
        flags.append(f"decodifica: {len(spans)} span corrotti ({where}) — evitarli nei tagli o coprirli")
    ad = inv.get("audio_decode") or {}
    nat, at = ad.get("native_aac_errors"), ad.get("aac_at_errors")
    if nat:
        where = ", ".join(s["label"] for s in (ad.get("native_aac_error_spans") or [])[:5])
        if ad.get("decision") == "native":
            flags.append(f"AAC: {nat} errori del decoder nativo ({where}), tutti accanto a span corrotti → decoder "
                         f"nativo (float); lì l'audio è silenzio: ascoltare quel punto prima di usarlo")
        else:
            flags.append(f"AAC: {nat} errori del decoder nativo ({where}) fuori dagli span corrotti → decoder aac_at "
                         f"({at} errori): picchi > 0 dBFS limitati a 0 dBFS; ascoltare quei punti")
    elif ad.get("decoder_errors"):
        flags.append(f"audio: {ad['decoder_errors']} errori di decodifica con {ad.get('decoder')}")
    if ad.get("wav_decoder_mismatch"):
        flags.append(f"audio16k/audio48k decodificati con {ad.get('decoder')} ma la decisione è {ad.get('decision')}: "
                     "yt-ingest --force per rigenerarli (poi yt-transcribe)")
    loud = inv.get("loudness") or {}
    bal = inv.get("lr_balance_db")
    if bal is not None and abs(bal) >= 3:
        side = "sinistro" if bal < 0 else "destro"
        flags.append(f"L/R sbilanciato: canale {side} più basso di {abs(bal):.1f} dB → mono-fold o pan (yt-loudnorm --balance auto)")
    prof = inv.get("lr_balance_profile") or {}
    if prof and prof["p90_db"] - prof["p10_db"] > 3:
        flags.append(f"L/R variabile nel tempo: L−R da {prof['p10_db']:+.1f} a {prof['p90_db']:+.1f} dB (p10–p90, "
                     f"finestre {prof['window_s']:g} s) → preferire mono-fold a un pan fisso")
    i = loud.get("integrated_lufs")
    if i is not None and abs(i - (-14)) > 1:
        flags.append(f"loudness integrata {i:+.1f} LUFS (YouTube normalizza a ~−14) → loudnorm a due passaggi")
    tp = loud.get("true_peak_dbtp")
    if tp is not None and tp > -1.0:
        flags.append(f"true peak {tp:+.1f} dBTP (> −1): rischio clipping in codifica")
    v = (inv.get("probe") or {}).get("video") or {}
    if v.get("hdr"):
        flags.append(f"HDR ({v.get('color_transfer')}): tonemap a BT.709 per consegne SDR")
    if v.get("vfr"):
        flags.append("frame rate variabile: conformare a CFR prima di sync/multicam")
    return flags


# ── Main ────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(prog="yt-ingest", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workdir", help="cartella di lavoro (path o <channel>/<dir>)")
    ap.add_argument("--source", help="chiave del sorgente da analizzare (default: main_source; "
                                     "gli altri sorgenti scrivono in analysis/source-<KEY>/)")
    ap.add_argument("--frames-every", type=float, default=20.0, metavar="N",
                    help="un frame campione ogni N secondi (default 20; 0 = nessuno)")
    ap.add_argument("--frame-width", type=int, default=960, help="larghezza dei frame campione (default 960)")
    px = ap.add_mutually_exclusive_group()
    px.add_argument("--proxy", action="store_true", help="crea il proxy anche se il sorgente è ≤1080p")
    px.add_argument("--no-proxy", action="store_true", help="non creare il proxy")
    ap.add_argument("--proxy-bitrate", default="3M", help="bitrate video del proxy (default 3M)")
    ap.add_argument("--no-integrity", action="store_true",
                    help="salta la decodifica completa (niente corrupt_spans; frame via seek)")
    ap.add_argument("--merge-gap", type=float, default=2.0, help="unisce errori più vicini di N s (default 2)")
    ap.add_argument("--sw", action="store_true", help="decodifica video software (senza VideoToolbox)")
    ap.add_argument("--force", action="store_true", help="rifà tutti i passi anche se gli output sono aggiornati")
    args = ap.parse_args()

    try:
        t_all = time.time()
        wd = ytcore.resolve_workdir(args.workdir)
        project = ytcore.load_project(wd)
        sources = project.get("sources") or {}
        if not sources:
            fail("project.json non ha sorgenti")
        key = args.source or project.get("main_source") or next(iter(sources))
        if key not in sources:
            fail(f"Sorgente '{key}' non presente in project.json ({', '.join(sources)})")
        src = Path(sources[key]["path"]).expanduser()
        if not src.exists():
            fail(f"Sorgente originale non trovato: {src}")
        is_main = key == (project.get("main_source") or next(iter(sources)))
        # Il sorgente principale usa analysis/; gli altri (camere, mic) una sottocartella,
        # così non sovrascrivono audio16k.wav & co. usati da trascrizione e montaggio.
        analysis = wd / "analysis" if is_main else wd / "analysis" / f"source-{key}"
        logs = wd / "logs"
        analysis.mkdir(parents=True, exist_ok=True)
        logs.mkdir(exist_ok=True)
        inv_path = analysis / "inventory.json"
        warnings: list[str] = []
        skipped: list[str] = []
        timings: dict = {}

        prev = {}
        if inv_path.exists() and not args.force:
            try:
                prev = ytcore.read_json(inv_path)
            except Exception:
                prev = {}
            ps = prev.get("source") or {}
            if ps.get("path") != str(src) or ps.get("sha256_fast") != sources[key].get("sha256_fast") \
                    or not _fresh([inv_path], src):
                prev = {}  # sorgente cambiato: niente riuso

        # 1) Probe (sempre: costa ~0,1 s).
        t0 = time.time()
        summary = probe_summary(src)
        others = {}
        for k, s in sources.items():
            if k == key:
                continue
            p = Path(s["path"]).expanduser()
            try:
                others[k] = probe_summary(p) if p.exists() else {"error": "file non trovato"}
            except Exception as exc:
                others[k] = {"error": str(exc)}
        timings["probe_s"] = round(time.time() - t0, 2)
        v, a = summary.get("video"), summary.get("audio")
        log(f"· {key}: {src.name} — {summary['duration']:.1f} s"
            + (f", {v['width']}x{v['height']} {v['codec']} {v['bits']}bit {v['fps'] or 0:g}fps" if v else "")
            + (f", {a['codec']} {a['sample_rate']} Hz {a['channels']}ch" if a else ""))

        a16, a48 = analysis / "audio16k.wav", analysis / "audio48k.wav"
        proxy_path = analysis / "proxy.mp4"
        frames_dir = analysis / "frames"
        frames_index = frames_dir / "index.json"
        contact = analysis / "contact.jpg"

        # 2) Decidi i passi.
        need_audio = bool(a) and (args.force or not _fresh([a16, a48], src) or "loudness" not in prev)
        is_aac = bool(a) and a["codec"] == "aac"
        prev_ad = prev.get("audio_decode") or {}
        # Decoder AAC (ytcore.aac_decoder_policy): la passata audio parte dal decoder già deciso per
        # questo sorgente (o forzato con YT_AAC_DECODER), altrimenti dal nativo; la decisione vera
        # arriva dopo l'integrità video e, se diversa, la passata si rifà.
        forced_dec = ytcore.aac_decoder_env() if is_aac else None
        recorded = None
        if is_aac:
            recorded = ((project.get("audio_decoder_by_source") or {}).get(key) or {}).get("decoder")
            if recorded is None and is_main:
                recorded = project.get("audio_decoder")
            recorded = recorded if recorded in ytcore.AAC_DECODERS else None
        first_dec = forced_dec or recorded or "native"
        # evidenze per la decisione: errori datati del nativo e conteggio di aac_at
        need_checks = is_aac and (need_audio or "native_aac_error_times" not in prev_ad
                                  or "aac_at_errors" not in prev_ad)
        big = bool(v) and min(v["width"] or 0, v["height"] or 0) > 1080
        want_proxy = bool(v) and not args.no_proxy and (args.proxy or big)
        # Senza un inventario valido dello STESSO sorgente (prev vuoto) proxy e frame si rifanno:
        # l'mtime da solo non basta se il sorgente è stato sostituito con un file più vecchio.
        need_proxy = want_proxy and (args.force or not prev or not _fresh([proxy_path], src))
        integ_done = "corrupt_spans" in (prev.get("integrity") or {})  # il segnaposto --no-integrity non conta
        need_integrity = bool(v) and not args.no_integrity and (args.force or not integ_done)
        prev_frames = {}
        if frames_index.exists():
            try:
                prev_frames = ytcore.read_json(frames_index)
            except Exception:
                prev_frames = {}
        need_frames = bool(v) and args.frames_every > 0 and (
            args.force or not prev or not _fresh([frames_index], src) or prev_frames.get("every") != args.frames_every
            or prev_frames.get("width") != args.frame_width or prev_frames.get("sampler") != SAMPLER_VERSION)
        run_video = need_integrity or need_proxy
        hw = not args.sw and bool(v) and vt_ok(summary)
        if v and not hw and not args.sw:
            warnings.append(f"codec {v['codec']} non decodificabile da VideoToolbox: decodifica software")

        # 3) Passate audio in un thread (CPU) mentre la passata video usa VideoToolbox.
        audio_res: dict = {}
        audio_err: list[BaseException] = []

        def audio_worker() -> None:
            try:
                if need_audio:
                    audio_res["main"] = audio_pass(src, summary, analysis, logs / "ingest-audio.log", first_dec)
                    t0b = time.time()
                    audio_res["main"]["lr_balance_profile"] = balance_profile(a48)
                    audio_res["main"]["elapsed_s"] = round(audio_res["main"]["elapsed_s"] + time.time() - t0b, 1)
                if need_checks:  # l'altro decoder (o entrambi, se i WAV sono già aggiornati)
                    done = (audio_res.get("main") or {}).get("decoder")
                    for dec in ytcore.AAC_DECODERS:
                        if dec != done:
                            audio_res[dec] = decoder_check(src, dec, logs / "ingest-audio.log")
            except BaseException as exc:  # riportato nel thread principale
                audio_err.append(exc)

        th = threading.Thread(target=audio_worker, daemon=True)
        th.start()

        video_res: dict = {}
        if run_video:
            what = [w for w, on in (("integrità", True), ("proxy", need_proxy and want_proxy),
                                    (f"frame/{args.frames_every:g}s", need_frames)) if on]
            log(f"· passata video unica ({'VideoToolbox' if hw else 'software'}): {', '.join(what)}")
            video_res = video_pass(src, summary, analysis, logs / "ingest-video.log",
                                   proxy=want_proxy and need_proxy,
                                   frames_every=args.frames_every if need_frames else 0,
                                   frame_width=args.frame_width, proxy_bitrate=args.proxy_bitrate,
                                   hw=hw, merge_gap=args.merge_gap, proxy_decoder=first_dec)
            if "integrity" not in video_res and hw:
                warnings.append("passata VideoToolbox fallita, ripeto in software: "
                                + video_res.get("tail", "")[-300:])
                video_res = video_pass(src, summary, analysis, logs / "ingest-video.log",
                                       proxy=want_proxy and need_proxy,
                                       frames_every=args.frames_every if need_frames else 0,
                                       frame_width=args.frame_width, proxy_bitrate=args.proxy_bitrate,
                                       hw=False, merge_gap=args.merge_gap, proxy_decoder=first_dec)
            if "integrity" not in video_res:
                th.join()
                fail(f"passata video fallita (exit {video_res.get('returncode')})",
                     tail=video_res.get("tail", "")[-1500:])
            timings["video_s"] = video_res["elapsed_s"]
            timings["video_speed_x"] = video_res["speed_x"]
        elif v:
            if args.no_integrity and not integ_done:
                skipped.append("video (--no-integrity" + (", proxy già aggiornato)" if want_proxy else ")"))
            else:
                skipped.append("video (integrità/proxy già fatti)")

        frames_items = video_res.get("frames")
        if frames_items is None and need_frames:
            # Nessuna passata video: frame via seek accurato (veloce con GOP corti).
            t0 = time.time()
            times = [round(k * args.frames_every, 3)
                     for k in range(int(summary["duration"] / args.frames_every + 1e-9) + 1)]
            tmp = analysis / ".frames.part"
            shutil.rmtree(tmp, ignore_errors=True)
            res = extract_at_times(src, times, tmp, summary=summary, fmt="jpg", hw=not args.sw,
                                   force=True, width=args.frame_width)
            frames_dir.mkdir(exist_ok=True)
            for old in frames_dir.glob("t_*.jpg"):
                old.unlink()
            frames_items = []
            for r in res:
                if r.get("file"):
                    Path(r["file"]).replace(frames_dir / Path(r["file"]).name)
                    frames_items.append({"t": r["t"], "file": Path(r["file"]).name})
            shutil.rmtree(tmp, ignore_errors=True)
            timings["frames_seek_s"] = round(time.time() - t0, 1)
        if frames_items is not None:
            ytcore.write_json(frames_index, {"every": args.frames_every, "width": args.frame_width, "source": key,
                                             "sampler": SAMPLER_VERSION, "frames": frames_items})
        elif v and args.frames_every > 0:
            skipped.append("frame (già aggiornati)")

        # 4) Contact sheet.
        if frames_index.exists() and (frames_items is not None or not _fresh([contact], src)
                                      or contact.stat().st_mtime < frames_index.stat().st_mtime):
            idx = ytcore.read_json(frames_index)
            t0 = time.time()
            contact_sheet([(f["t"], frames_dir / f["file"]) for f in idx["frames"]], contact,
                          title=f"{project.get('channel')}/{wd.name} · {src.name} · ogni {idx['every']:g} s")
            timings["contact_s"] = round(time.time() - t0, 2)

        th.join()
        if audio_err:
            raise audio_err[0]
        for k in ("main", "native", "aac_at"):
            if k in audio_res:
                timings[f"audio_{k}_s"] = audio_res[k]["elapsed_s"]
        if a and not need_audio:
            skipped.append("audio (wav e loudness già aggiornati)")

        # 5) Inventario (riusa i risultati dei passi saltati).
        inv = {
            "version": 1,
            "generated": dt.datetime.now().isoformat(timespec="seconds"),
            "source": {"key": key, "path": str(src), "link": sources[key].get("link"),
                       "sha256_fast": sources[key].get("sha256_fast"), "size": summary["size"]},
            "probe": summary,
            "sources": others,
        }
        if "integrity" in video_res:
            inv["integrity"] = video_res["integrity"]
        elif integ_done:
            inv["integrity"] = prev["integrity"]
        elif v:
            inv["integrity"] = {"skipped": True, "note": "--no-integrity: decodifica completa non eseguita"}
        inv["corrupt_spans"] = (inv.get("integrity") or {}).get("corrupt_spans", [])

        # 5a) Decoder AAC: evidenze (passata audio + controlli), decisione, eventuale nuova passata.
        ad = dict(prev_ad)  # conserva le misure dei passi non rifatti
        main_a = audio_res.get("main")
        if main_a:
            ad.update(_audio_decode_fields(main_a, summary))
        for dec in ytcore.AAC_DECODERS:
            if dec in audio_res:
                ad.update(_check_fields(audio_res[dec]))
        if is_aac:
            integ = inv.get("integrity") or {}
            spans_known = "corrupt_spans" in integ
            d = ytcore.decide_aac_decoder(ad.get("native_aac_errors"), ad.get("native_aac_error_times"),
                                          integ.get("corrupt_spans") if spans_known else None,
                                          native_error_spans=ad.get("native_aac_error_spans"))
            ad.update({"decision": d["decoder"], "decision_reason": d["reason"], "decision_margin_s": d["margin_s"],
                       "decision_outside_corrupt": d["outside_corrupt"], "corrupt_spans_checked": spans_known,
                       "override": forced_dec, "recommended_decoder": d["decoder"],
                       "policy": "ytcore.aac_decoder_policy: project.json audio_decoder, env YT_AAC_DECODER",
                       "note": "aac_at (AudioToolbox) decodifica sempre in s16: i picchi > 0 dBFS vengono limitati "
                               "a 0 dBFS; il decoder nativo (aac) decodifica in float"})
            target = forced_dec or d["decoder"]
            log(f"· decoder AAC: {d['decoder']} — {d['reason']}" + (f" (forzato {target})" if forced_dec else ""))
            if ad.get("decoder") != target:
                transcript = (wd / "analysis" / "transcript.words.json").exists() and is_main
                if main_a or not transcript:
                    log(f"· WAV decodificati con {ad.get('decoder')}: rifaccio la passata audio con {target}")
                    t0 = time.time()
                    main_a = audio_pass(src, summary, analysis, logs / "ingest-audio.log", target)
                    main_a["lr_balance_profile"] = balance_profile(a48)
                    timings["audio_redo_s"] = round(time.time() - t0, 1)
                    ad.update(_audio_decode_fields(main_a, summary))
                    ad.pop("wav_decoder_mismatch", None)
                    skipped[:] = [x for x in skipped if not x.startswith("audio (")]
                else:
                    ad["wav_decoder_mismatch"] = True
                    warnings.append(f"audio16k/audio48k fatti con {ad.get('decoder')}, decisione {target}: "
                                    "non rigenerati perché c'è già un transcript (yt-ingest --force, poi yt-transcribe)")
            else:
                ad.pop("wav_decoder_mismatch", None)
        if main_a:
            inv["loudness"] = main_a["loudness"]
            inv["lr_balance_db"] = main_a["lr_balance_db"]
            inv["lr_balance_profile"] = main_a.get("lr_balance_profile")
        elif "loudness" in prev:
            inv["loudness"] = prev["loudness"]
            inv["lr_balance_db"] = prev.get("lr_balance_db")
            inv["lr_balance_profile"] = prev.get("lr_balance_profile")
        if video_res.get("proxy_audio_decoder"):
            ad["proxy_audio_decoder"] = video_res["proxy_audio_decoder"]
        if a:
            inv["audio_decode"] = ad
        inv["lr_balance_note"] = ("lr_balance_db = RMS(L) − RMS(R) in dB sull'intero file; negativo = canale sinistro "
                                  "più basso. lr_balance_profile = stessa misura per finestre (solo finestre con segnale)")
        # Incrocio: errori AAC nativi dentro gli span video corrotti.
        for sp in inv["corrupt_spans"]:
            sp["native_aac_errors_nearby"] = sum(
                s["errors"] for s in ad.get("native_aac_error_spans", [])
                if s["start"] <= sp["end"] + 2 and s["end"] >= sp["start"] - 2)

        outputs = {}
        for name, p in (("inventory", inv_path), ("audio16k", a16), ("audio48k", a48), ("proxy", proxy_path),
                        ("frames_index", frames_index), ("contact", contact)):
            if p.exists():
                outputs[name] = str(p.relative_to(wd))
        if frames_index.exists():
            outputs["frames_dir"] = str(frames_dir.relative_to(wd))
            fi = ytcore.read_json(frames_index)
            inv["frames"] = {"every": fi["every"], "width": fi["width"], "count": len(fi["frames"])}
        outputs["inventory"] = str(inv_path.relative_to(wd))
        inv["outputs"] = outputs
        inv["flags"] = build_flags(inv)
        timings["total_s"] = round(time.time() - t_all, 1)
        inv["timings"] = {**(prev.get("timings") or {}), **timings}
        ytcore.write_json(inv_path, inv)

        status = project.get("status") or "new"
        proj_fields: dict = {}
        if a:  # decisione sul decoder: la leggono tutti gli altri comandi (ytcore.aac_decoder_policy)
            if is_aac:
                entry = {"decoder": ad["decision"], "reason": ad["decision_reason"]}
            else:
                entry = {"decoder": "native", "reason": f"audio {a['codec']}: aac_at serve solo per AAC"}
            entry["decided"] = dt.datetime.now().isoformat(timespec="seconds")
            proj_fields["audio_decoder_by_source"] = {key: entry}
            if is_main:
                proj_fields["audio_decoder"] = entry["decoder"]
                proj_fields["audio_decoder_reason"] = entry["reason"]
        if is_main and (status not in STATUS_ORDER or STATUS_ORDER.index(status) < STATUS_ORDER.index("ingested")):
            proj_fields["status"] = "ingested"
        if proj_fields:
            ytcore.update_project(wd, **proj_fields)
        for f in inv["flags"]:
            log(f"  ⚑ {f}")
        log(f"✓ ingest in {timings['total_s']} s → {inv_path}")
        emit(True, workdir=str(wd), source=key, outputs=outputs, corrupt_spans=inv["corrupt_spans"],
             loudness={k: (inv.get("loudness") or {}).get(k) for k in
                       ("integrated_lufs", "lra_lu", "true_peak_dbtp", "sample_peak_dbfs")},
             lr_balance_db=inv.get("lr_balance_db"),
             lr_balance_profile={k: v for k, v in (inv.get("lr_balance_profile") or {}).items() if k != "windows"},
             audio_decode={k: ad.get(k) for k in
                           ("decoder", "decision", "decision_reason", "override", "decoder_errors",
                            "native_aac_errors", "native_aac_error_times", "aac_at_errors", "native_sample_peak_dbfs",
                            "aac_at_sample_peak_dbfs", "wav_duration_s", "container_audio_duration_s",
                            "wav_delta_ms", "wav_decoder_mismatch") if ad.get(k) is not None} if a else None,
             flags=inv["flags"], timings=timings, skipped=skipped, warnings=warnings)
    except SystemExit:
        raise
    except Exception as exc:
        log(f"✗ {exc}")
        fail(str(exc))


if __name__ == "__main__":
    main()

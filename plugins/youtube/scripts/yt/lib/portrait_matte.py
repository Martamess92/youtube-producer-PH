"""Worker di matting per yt-portrait: gira nel venv rembg (~/.venvs/rembg), mai nel venv del toolkit.

Uso (lo lancia lib/portrait.py, non a mano):
  REMBG_HOME=~/.venvs/rembg/home ~/.venvs/rembg/bin/python -I portrait_matte.py JOB.json
JOB.json: {"region": "r.npy" (float32 H×W×3, sRGB 0–1), "face": [x,y,w,h] px della regione,
           "exclude": [[x,y,w,h], …], "out_alpha": "a.npy", "out_fg": "f.npy", "head_tile": true}
stdout: un JSON {"ok", "model", "timings_s", …}.

Passi: BiRefNet-portrait sulla regione del busto + su una tile della testa a ~1:1
(fusione con rampa di 24 px), solo le componenti che toccano il volto, zone escluse (PiP) a zero, α ≥ 0.97 → 1 e
α ≤ 0.01 → 0; colore di primo piano con pymatting estimate_foreground_ml (risolve I = αF + (1−α)B).
Solo il modello birefnet-portrait già presente nel venv: se manca il file, errore (mai download, mai
bria-rmbg di default, mai backend cloud, mai MODEL_CHECKSUM_DISABLED).
"""
import json
import os
import sys
import time
from pathlib import Path

MODEL = "birefnet-portrait"


def main() -> None:
    job = json.loads(Path(sys.argv[1]).read_text())
    home = os.environ.get("REMBG_HOME", "")
    os.environ.pop("U2NET_HOME", None)
    model = Path(home) / "models" / MODEL / f"{MODEL}.onnx"
    if not home or not model.exists() or model.stat().st_size < 100_000_000:
        print(json.dumps({"ok": False, "error": f"modello {MODEL} assente in {model} (nessun download automatico)"}))
        sys.exit(2)
    if os.environ.get("MODEL_CHECKSUM_DISABLED"):
        print(json.dumps({"ok": False, "error": "MODEL_CHECKSUM_DISABLED non ammesso"}))
        sys.exit(2)

    import numpy as np
    from PIL import Image
    from scipy import ndimage
    from pymatting import estimate_foreground_ml
    from rembg import new_session, remove

    T = {}
    t0 = time.time()
    reg = np.load(job["region"]).astype(np.float64)
    H, W = reg.shape[:2]
    fx, fy, fw, fh = [float(v) for v in job["face"]]
    session = new_session(MODEL, providers=["CPUExecutionProvider"])
    T["load"] = time.time() - t0

    def alpha_of(rgb):
        im = Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8))
        m = remove(im, session=session, only_mask=True, post_process_mask=False)
        return np.asarray(m, np.float64) / 255.0

    t0 = time.time()
    alpha = alpha_of(reg)
    for ex in job.get("exclude") or []:
        x, y, w, h = [int(round(v)) for v in ex]
        alpha[max(0, y):max(0, y + h), max(0, x):max(0, x + w)] = 0
    tiles = 0
    if job.get("head_tile", True):
        hx0, hx1 = int(max(0, fx + fw / 2 - 1.3 * fw)), int(min(W, fx + fw / 2 + 1.3 * fw))
        hy0, hy1 = int(max(0, fy - 1.2 * fh)), int(min(H, fy + 1.6 * fh))
        if hx1 - hx0 > 32 and hy1 - hy0 > 32:
            a_head = alpha_of(reg[hy0:hy1, hx0:hx1])
            ramp = np.ones(a_head.shape)
            k = 24
            for i in range(k):
                f = (i + 1) / (k + 1)
                if hx0 > 0:
                    ramp[:, i] = np.minimum(ramp[:, i], f)
                if hx1 < W:
                    ramp[:, -1 - i] = np.minimum(ramp[:, -1 - i], f)
                if hy0 > 0:
                    ramp[i, :] = np.minimum(ramp[i, :], f)
                if hy1 < H:
                    ramp[-1 - i, :] = np.minimum(ramp[-1 - i, :], f)
            blk = alpha[hy0:hy1, hx0:hx1]
            alpha[hy0:hy1, hx0:hx1] = blk * (1 - ramp) + a_head * ramp
            for ex in job.get("exclude") or []:
                x, y, w, h = [int(round(v)) for v in ex]
                alpha[max(0, y):max(0, y + h), max(0, x):max(0, x + w)] = 0
            tiles = 1
    # solo le componenti che toccano il volto (spalla di un vicino, PiP, oggetti)
    lab, n = ndimage.label(alpha > 0.5)
    kept = n
    if n > 1:
        sel = np.unique(lab[int(fy):int(fy + fh), int(fx):int(fx + fw)])
        sel = sel[sel > 0]
        if len(sel):
            keep = ndimage.binary_dilation(np.isin(lab, sel), iterations=4)
            alpha = alpha * keep
            kept = int(len(sel))
    alpha = np.where(alpha >= 0.97, 1.0, np.where(alpha <= 0.01, 0.0, alpha))
    T["matting"] = time.time() - t0
    t0 = time.time()
    fg = estimate_foreground_ml(reg, alpha)
    T["foreground_ml"] = time.time() - t0
    np.save(job["out_alpha"], alpha.astype(np.float32))
    np.save(job["out_fg"], np.clip(fg, 0, 1).astype(np.float32))
    print(json.dumps({"ok": True, "model": MODEL, "model_bytes": model.stat().st_size, "head_tiles": tiles,
                      "components": int(n), "kept": kept, "timings_s": {k: round(v, 2) for k, v in T.items()}}))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — il chiamante legge il JSON
        import traceback
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
        sys.exit(1)

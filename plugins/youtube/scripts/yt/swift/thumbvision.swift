// thumbvision.swift — helper Apple Vision per le thumbnail di YouTube Producer.
// Zero install: solo framework di sistema (Vision, CoreImage, ImageIO). Nessuna chiamata di rete.
// macOS 14+ (maschere persona/soggetto), estetica solo su macOS 15+.
//
// Compilazione:  swiftc -O swift/thumbvision.swift -o bin/thumbvision
//
// Sottocomandi (stdout = JSON, log su stderr):
//   thumbvision score  IMG... [--roi x,y,w,h] [--list FILE] [--no-aesthetics] [--no-identity] [--debug]
//   thumbvision faces  IMG... [--roi x,y,w,h] [--list FILE] [--bodies]
//   thumbvision cutout IMG --out PNG [--mode person|subject] [--instance largest|center|all|N[,N]]
//                      [--point x,y] [--roi x,y,w,h] [--exclude x,y,w,h[;…]] [--matte auto|instance|accurate]
//                      [--feather PX] [--choke PX] [--decontam PX] [--trim] [--pad PX] [--mask-out PNG]
//   thumbvision saliency IMG... [--list FILE] [--mode attention|objectness] [--out PNG | --out-dir DIR]
//                      [--boxes nome:x,y,w,h[;…]] [--overlay]
//   thumbvision version
//
// 1.1.0 (thumbnail v2): `score` aggiunge per ogni volto "geom" (geometria dell'espressione dai
// landmark: sollevamento degli angoli della bocca, larghezza bocca, spessore labbra, sopracciglia, asimmetrie),
// letta da lib/expressions.py per le classi di espressione; nuovo `saliency` (Apple Vision attention-based
// saliency → heatmap + regione principale + quota di salienza dentro box nominati, per la QA: volto o frase?).
//
// Coordinate: box e punti normalizzati 0–1 rispetto all'immagine INTERA, origine in alto a sinistra
// (schema design §8.3). --roi accetta valori normalizzati (tutti ≤1) oppure pixel.
//
// Correzioni rispetto al primo prototipo:
//  1. qualità ↔ landmark associati sulla stessa osservazione (inputFaceObservations + match per IoU);
//  2. apertura occhi normalizzata per persona sull'insieme di immagini passate nella stessa chiamata
//     (identità stimata con feature print del volto), con z-score;
//  3. cutout 'person' (VNGeneratePersonInstanceMaskRequest + matte accurato) e 'subject'
//     (VNGenerateForegroundInstanceMaskRequest), con scelta dell'istanza;
//  4. apertura bocca da innerLips/outerLips.
import Foundation
import Vision
import CoreImage
import CoreImage.CIFilterBuiltins
import ImageIO
import UniformTypeIdentifiers

let VERSION = "1.1.0"

// MARK: - Utilità I/O

func logErr(_ s: String) { FileHandle.standardError.write((s + "\n").data(using: .utf8)!) }

func printJSON(_ obj: Any) {
    let opts: JSONSerialization.WritingOptions = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    guard let data = try? JSONSerialization.data(withJSONObject: obj, options: opts),
          var s = String(data: data, encoding: .utf8) else { return }
    // JSONSerialization stampa i Double con 17 cifre (0.42399999999999999): li riportiamo a 4 decimali.
    if let re = try? NSRegularExpression(pattern: "-?\\d+\\.\\d{6,}") {
        let ns = s as NSString
        var out = "", last = 0
        for m in re.matches(in: s, range: NSRange(location: 0, length: ns.length)) {
            out += ns.substring(with: NSRange(location: last, length: m.range.location - last))
            let v = Double(ns.substring(with: m.range)) ?? 0
            var t = String(format: "%.4f", v)
            while t.hasSuffix("0") { t.removeLast() }
            if t.hasSuffix(".") { t.removeLast() }
            out += t
            last = m.range.location + m.range.length
        }
        out += ns.substring(from: last)
        s = out
    }
    print(s)
}

func die(_ msg: String, code: Int32 = 1) -> Never {
    printJSON(["ok": false, "error": msg])
    exit(code)
}

func r4(_ v: Double) -> Double { (v * 10000).rounded() / 10000 }
func r4(_ v: CGFloat) -> Double { r4(Double(v)) }
func clamp01(_ v: Double) -> Double { max(0, min(1, v)) }

/// Carica l'immagine applicando l'orientamento EXIF (foto da telefono) → pixel "dritti".
func loadImage(_ path: String) -> CGImage? {
    let url = URL(fileURLWithPath: path)
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
    let props = CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [CFString: Any]
    let orient = (props?[kCGImagePropertyOrientation] as? NSNumber)?.intValue ?? 1
    if orient == 1 { return CGImageSourceCreateImageAtIndex(src, 0, nil) }
    let w = (props?[kCGImagePropertyPixelWidth] as? NSNumber)?.intValue ?? 0
    let h = (props?[kCGImagePropertyPixelHeight] as? NSNumber)?.intValue ?? 0
    let opts: [CFString: Any] = [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceCreateThumbnailWithTransform: true,
        kCGImageSourceThumbnailMaxPixelSize: max(w, h, 1),
    ]
    return CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary)
}

/// Rettangolo in pixel (origine in alto a sinistra) da "x,y,w,h" normalizzato o in pixel.
func parseRect(_ s: String, width: Int, height: Int) -> CGRect? {
    let v = s.split(separator: ",").compactMap { Double($0.trimmingCharacters(in: .whitespaces)) }
    guard v.count == 4 else { return nil }
    let normalized = v.allSatisfy { $0 <= 1.0 }
    let r = normalized
        ? CGRect(x: v[0] * Double(width), y: v[1] * Double(height), width: v[2] * Double(width), height: v[3] * Double(height))
        : CGRect(x: v[0], y: v[1], width: v[2], height: v[3])
    let full = CGRect(x: 0, y: 0, width: width, height: height)
    let clipped = r.integral.intersection(full)
    return clipped.isEmpty ? nil : clipped
}

func parsePoint(_ s: String) -> CGPoint? {
    let v = s.split(separator: ",").compactMap { Double($0.trimmingCharacters(in: .whitespaces)) }
    guard v.count == 2 else { return nil }
    return CGPoint(x: v[0], y: v[1])
}

/// Argomenti: posizionali + opzioni --chiave valore / --flag.
struct Args {
    var positional: [String] = []
    var options: [String: String] = [:]
    var flags: Set<String> = []
    init(_ raw: [String], valued: Set<String>) {
        var i = 0
        while i < raw.count {
            let a = raw[i]
            if a.hasPrefix("--") {
                let key = String(a.dropFirst(2))
                if let eq = key.firstIndex(of: "=") {
                    options[String(key[..<eq])] = String(key[key.index(after: eq)...])
                } else if valued.contains(key), i + 1 < raw.count {
                    options[key] = raw[i + 1]; i += 1
                } else {
                    flags.insert(key)
                }
            } else {
                positional.append(a)
            }
            i += 1
        }
    }
}

func expandInputs(_ args: Args) -> [String] {
    var files = args.positional
    if let list = args.options["list"], let text = try? String(contentsOfFile: list, encoding: .utf8) {
        files += text.split(whereSeparator: \.isNewline).map { String($0).trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
    }
    return files
}

// MARK: - Geometria Vision → immagine

/// Box Vision (normalizzato al crop, origine in basso a sinistra) → box normalizzato all'immagine intera, origine in alto a sinistra.
func toFullNorm(_ nbox: CGRect, crop: CGRect, fullW: Int, fullH: Int) -> [Double] {
    let px = crop.minX + nbox.minX * crop.width
    let py = crop.minY + (1 - nbox.maxY) * crop.height
    return [r4(px / CGFloat(fullW)), r4(py / CGFloat(fullH)), r4(nbox.width * crop.width / CGFloat(fullW)), r4(nbox.height * crop.height / CGFloat(fullH))]
}

func iou(_ a: CGRect, _ b: CGRect) -> Double {
    let i = a.intersection(b)
    if i.isNull || i.isEmpty { return 0 }
    let inter = Double(i.width * i.height)
    return inter / (Double(a.width * a.height) + Double(b.width * b.height) - inter)
}

/// Rapporto altezza/larghezza di un contorno misurato lungo il suo asse principale
/// (gli estremi più lontani = angoli): insensibile al rollio della testa.
func axisAspect(_ pts: [CGPoint]) -> (ratio: Double, width: Double)? {
    guard pts.count >= 4 else { return nil }
    var a = pts[0], b = pts[1], best: CGFloat = -1
    for i in 0..<pts.count {
        for j in (i + 1)..<pts.count {
            let d = hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y)
            if d > best { best = d; a = pts[i]; b = pts[j] }
        }
    }
    guard best > 0 else { return nil }
    let ux = (b.x - a.x) / best, uy = (b.y - a.y) / best
    var lo = CGFloat.greatestFiniteMagnitude, hi = -CGFloat.greatestFiniteMagnitude
    for p in pts {
        let perp = -(p.x - a.x) * uy + (p.y - a.y) * ux
        lo = min(lo, perp); hi = max(hi, perp)
    }
    return (Double((hi - lo) / best), Double(best))
}

// MARK: - Nitidezza (varianza del laplaciano su grigio 8 bit)

func grayBuffer(_ cg: CGImage, width: Int, height: Int) -> [UInt8] {
    var buf = [UInt8](repeating: 0, count: width * height)
    buf.withUnsafeMutableBytes { raw in
        guard let ctx = CGContext(data: raw.baseAddress, width: width, height: height, bitsPerComponent: 8,
                                  bytesPerRow: width, space: CGColorSpaceCreateDeviceGray(),
                                  bitmapInfo: CGImageAlphaInfo.none.rawValue) else { return }
        ctx.interpolationQuality = .high
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))
    }
    return buf
}

func laplacianVariance(_ g: [UInt8], _ w: Int, _ h: Int) -> Double {
    guard w > 2, h > 2 else { return 0 }
    var sum = 0.0, sumSq = 0.0, n = 0.0
    g.withUnsafeBufferPointer { p in
        for y in 1..<(h - 1) {
            let row = y * w
            for x in 1..<(w - 1) {
                let c = row + x
                let l = 4 * Int(p[c]) - Int(p[c - 1]) - Int(p[c + 1]) - Int(p[c - w]) - Int(p[c + w])
                let d = Double(l)
                sum += d; sumSq += d * d; n += 1
            }
        }
    }
    let mean = sum / n
    return sumSq / n - mean * mean
}

/// Nitidezza dell'immagine a larghezza fissa 1280 px (confrontabile tra immagini di dimensioni diverse).
func imageSharpness(_ cg: CGImage) -> Double {
    let w = 1280, h = max(3, Int((Double(cg.height) / Double(cg.width) * 1280).rounded()))
    return laplacianVariance(grayBuffer(cg, width: w, height: h), w, h)
}

/// Nitidezza del volto: crop del box (pixel, origine in alto) ricampionato a 256 px di altezza.
func regionSharpness(_ cg: CGImage, _ rect: CGRect) -> Double? {
    guard let crop = cg.cropping(to: rect.integral), crop.width > 8, crop.height > 8 else { return nil }
    let h = 256, w = max(3, Int((Double(crop.width) / Double(crop.height) * 256).rounded()))
    return laplacianVariance(grayBuffer(crop, width: w, height: h), w, h)
}

// MARK: - score

struct FaceRec {
    var file: Int
    var data: [String: Any]
    var eyeRatio: Double?      // media dei due occhi
    var print: VNFeaturePrintObservation?
    var quality: Double
    var mouthOpen: Double
    var yaw: Double
}

/// Apertura occhi assoluta (fallback senza normalizzazione per persona). Tarata su volti ~250 px.
func eyesAbsolute(_ ratio: Double) -> Double { clamp01((ratio - 0.11) / (0.26 - 0.11)) }

func featurePrint(_ cg: CGImage, rect: CGRect) -> VNFeaturePrintObservation? {
    // Volto allargato (capelli, occhiali, barba) per un'identità più stabile.
    let grow = rect.insetBy(dx: -rect.width * 0.3, dy: -rect.height * 0.3)
        .intersection(CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
    guard let crop = cg.cropping(to: grow.integral) else { return nil }
    let req = VNGenerateImageFeaturePrintRequest()
    req.imageCropAndScaleOption = .scaleFit
    try? VNImageRequestHandler(cgImage: crop, options: [:]).perform([req])
    return req.results?.first
}

/// Geometria dell'espressione dai landmark Vision (thumbnail v2, T3 fase A). Nessuna soglia qui: valori grezzi,
/// normalizzati per persona ed episodio in lib/expressions.py (z-score robusti).
/// Coordinate del volto: x dall'occhio a sinistra nell'immagine a quello a destra, y verso l'alto (pointsInImage ha
/// l'origine in basso a sinistra), origine nel punto medio degli occhi. Misure verticali ÷ altezza del box del volto
/// (stabile con lo yaw), orizzontali ÷ distanza interoculare (si accorciano entrambe con cos(yaw)).
///   smile_lift  angoli della bocca sopra la metà dell'altezza delle labbra (> 0 = sorriso, < 0 = angoli giù)
///   corner_asym angolo destro − sinistro (in alto = positivo): sorriso storto, smorfia
///   mouth_w     larghezza della bocca ÷ interoculare (il sorriso la allarga)
///   mouth_h     altezza esterna delle labbra ÷ altezza volto;  lip_thick: (esterna − apertura interna) ÷ altezza volto
///   nose_lip    base del naso − bordo alto del labbro superiore ÷ altezza volto (si accorcia nel sorriso a denti scoperti)
///   brow_l/r    sopracciglio (baricentro) sopra l'occhio dello stesso lato; brow_inner: i due punti interni
///   brow_asym   |brow_l − brow_r|
func faceGeometry(_ L: VNFaceLandmarks2D, imgSize: CGSize, faceH: CGFloat) -> [String: Any]? {
    guard faceH > 1, let le = L.leftEye?.pointsInImage(imageSize: imgSize), let re = L.rightEye?.pointsInImage(imageSize: imgSize),
          le.count >= 3, re.count >= 3 else { return nil }
    func centroid(_ p: [CGPoint]) -> CGPoint {
        CGPoint(x: p.map(\.x).reduce(0, +) / CGFloat(p.count), y: p.map(\.y).reduce(0, +) / CGFloat(p.count))
    }
    var e1 = centroid(le), e2 = centroid(re)
    if e1.x > e2.x { swap(&e1, &e2) }
    let iod = hypot(e2.x - e1.x, e2.y - e1.y)
    guard iod > 1 else { return nil }
    let ux = (e2.x - e1.x) / iod, uy = (e2.y - e1.y) / iod
    let ox = (e1.x + e2.x) / 2, oy = (e1.y + e2.y) / 2
    func proj(_ p: CGPoint) -> (x: Double, y: Double) {
        let dx = p.x - ox, dy = p.y - oy
        return (Double(dx * ux + dy * uy), Double(-dx * uy + dy * ux))
    }
    let H = Double(faceH), D = Double(iod)
    var g: [String: Any] = ["iod_px": r4(D)]
    let p1 = proj(e1), p2 = proj(e2)
    if let outer = L.outerLips?.pointsInImage(imageSize: imgSize), outer.count >= 6 {
        let q = outer.map(proj)
        let cl = q.min(by: { $0.x < $1.x })!, cr = q.max(by: { $0.x < $1.x })!
        let top = q.map(\.y).max()!, bot = q.map(\.y).min()!
        let mid = (top + bot) / 2
        g["smile_lift"] = r4(((cl.y + cr.y) / 2 - mid) / H)
        g["corner_asym"] = r4((cr.y - cl.y) / H)
        g["mouth_w"] = r4((cr.x - cl.x) / D)
        g["mouth_h"] = r4((top - bot) / H)
        var innerH = 0.0
        if let inner = L.innerLips?.pointsInImage(imageSize: imgSize), inner.count >= 3 {
            let qi = inner.map(proj)
            innerH = qi.map(\.y).max()! - qi.map(\.y).min()!
        }
        g["lip_thick"] = r4(max(0, (top - bot) - innerH) / H)
        // labbro superiore → base del naso: si accorcia quando il labbro sale e scopre i denti (AU10, sorriso aperto)
        if let nose = L.nose?.pointsInImage(imageSize: imgSize), nose.count >= 3 {
            g["nose_lip"] = r4((nose.map(proj).map(\.y).min()! - top) / H)
        }
    }
    var brows: [Double] = [], inners: [Double] = []
    for b in [L.leftEyebrow, L.rightEyebrow] {
        guard let pts = b?.pointsInImage(imageSize: imgSize), pts.count >= 3 else { continue }
        let q = pts.map(proj)
        let cx = q.map(\.x).reduce(0, +) / Double(q.count)
        let cy = q.map(\.y).reduce(0, +) / Double(q.count)
        let eyeY = cx < 0 ? p1.y : p2.y
        let inner = q.sorted(by: { abs($0.x) < abs($1.x) }).prefix(2)
        let iy = inner.map(\.y).reduce(0, +) / Double(inner.count)
        if cx < 0 { g["brow_l"] = r4((cy - eyeY) / H) } else { g["brow_r"] = r4((cy - eyeY) / H) }
        brows.append((cy - eyeY) / H)
        inners.append((iy - eyeY) / H)
    }
    if !brows.isEmpty { g["brow_mean"] = r4(brows.reduce(0, +) / Double(brows.count)) }
    if !inners.isEmpty { g["brow_inner"] = r4(inners.reduce(0, +) / Double(inners.count)) }
    if let bl = g["brow_l"] as? Double, let br = g["brow_r"] as? Double { g["brow_asym"] = r4(abs(bl - br)) }
    return g
}

func cmdScore(_ args: Args) {
    let files = expandInputs(args)
    if files.isEmpty { die("score: nessuna immagine (usa: thumbvision score IMG... [--roi x,y,w,h])", code: 64) }
    let doAesthetics = !args.flags.contains("no-aesthetics")
    let doIdentity = !args.flags.contains("no-identity")
    let debug = args.flags.contains("debug")

    var results: [[String: Any]] = []
    var faces: [FaceRec] = []

    for (fi, path) in files.enumerated() {
        var out: [String: Any] = ["file": path]
        guard let full = loadImage(path) else {
            out["error"] = "impossibile leggere l'immagine"; out["faces"] = [Any](); results.append(out); continue
        }
        let fullW = full.width, fullH = full.height
        var crop = CGRect(x: 0, y: 0, width: fullW, height: fullH)
        if let roiS = args.options["roi"] {
            guard let r = parseRect(roiS, width: fullW, height: fullH) else { die("--roi non valida: \(roiS)", code: 64) }
            crop = r
            out["roi"] = [r4(r.minX / CGFloat(fullW)), r4(r.minY / CGFloat(fullH)), r4(r.width / CGFloat(fullW)), r4(r.height / CGFloat(fullH))]
        }
        guard let work = (crop.size == CGSize(width: fullW, height: fullH)) ? full : full.cropping(to: crop) else {
            out["error"] = "crop fallito"; out["faces"] = [Any](); results.append(out); continue
        }
        out["w"] = fullW; out["h"] = fullH
        let handler = VNImageRequestHandler(cgImage: work, options: [:])

        // 1) rettangoli (rilevatore rev. 3: yaw/pitch continui) → 2) landmark e 3) qualità sulle STESSE osservazioni.
        let rects = VNDetectFaceRectanglesRequest()
        do { try handler.perform([rects]) } catch {
            out["error"] = "vision: \(error.localizedDescription)"; out["faces"] = [Any](); results.append(out); continue
        }
        let landmarks = VNDetectFaceLandmarksRequest()
        landmarks.inputFaceObservations = rects.results ?? []
        try? handler.perform([landmarks])
        let lmObs = landmarks.results ?? []
        let quality = VNDetectFaceCaptureQualityRequest()
        quality.inputFaceObservations = lmObs
        var reqs: [VNRequest] = [quality]
        var aestheticsReq: VNRequest? = nil
        if doAesthetics, #available(macOS 15.0, *) {
            let a = VNCalculateImageAestheticsScoresRequest(); reqs.append(a); aestheticsReq = a
        }
        try? handler.perform(reqs)
        let qObs = quality.results ?? []

        let imgSize = CGSize(width: work.width, height: work.height)
        var faceList: [[String: Any]] = []
        for lm in lmObs {
            // Associazione: stesso uuid se preservato, altrimenti massimo IoU (mai per indice).
            let q = qObs.first(where: { $0.uuid == lm.uuid })
                ?? qObs.max(by: { iou($0.boundingBox, lm.boundingBox) < iou($1.boundingBox, lm.boundingBox) })
            let qv = (q.map { iou($0.boundingBox, lm.boundingBox) > 0.5 } ?? false) ? Double(q!.faceCaptureQuality ?? -1) : -1
            let fbox = lm.boundingBox
            var d: [String: Any] = [
                "box": toFullNorm(fbox, crop: crop, fullW: fullW, fullH: fullH),
                "quality": qv >= 0 ? r4(qv) : NSNull(),
                "confidence": r4(Double(lm.confidence)),
                "face_px": Int((fbox.height * crop.height).rounded()),
            ]
            if let yaw = lm.yaw { d["yaw"] = r4(yaw.doubleValue * 180 / .pi) }
            if let roll = lm.roll { d["roll"] = r4(roll.doubleValue * 180 / .pi) }
            if #available(macOS 12.0, *), let pitch = lm.pitch { d["pitch"] = r4(pitch.doubleValue * 180 / .pi) }

            var eyeRatio: Double? = nil
            var mouthOpen = 0.0
            if let L = lm.landmarks {
                let le = L.leftEye.flatMap { axisAspect($0.pointsInImage(imageSize: imgSize)) }
                let re = L.rightEye.flatMap { axisAspect($0.pointsInImage(imageSize: imgSize)) }
                if let le { d["eye_ratio_l"] = r4(le.ratio) }
                if let re { d["eye_ratio_r"] = r4(re.ratio) }
                let rs = [le?.ratio, re?.ratio].compactMap { $0 }
                if !rs.isEmpty {
                    // Di profilo la larghezza dell'occhio si accorcia (≈cos yaw) e il rapporto cresce:
                    // correzione parziale (radice) perché l'occhio vicino si accorcia meno.
                    let yawDeg = abs(lm.yaw?.doubleValue ?? 0) * 180 / .pi
                    eyeRatio = rs.reduce(0, +) / Double(rs.count) * sqrt(cos(min(yawDeg, 75) * .pi / 180))
                }
                // Bocca: apertura interna rispetto alla larghezza delle labbra esterne.
                if let inner = L.innerLips?.pointsInImage(imageSize: imgSize),
                   let outer = L.outerLips?.pointsInImage(imageSize: imgSize),
                   let oa = axisAspect(outer), let ia = axisAspect(inner), oa.width > 0 {
                    let mar = ia.ratio * ia.width / oa.width
                    d["mouth_ratio"] = r4(mar)
                    mouthOpen = clamp01((mar - 0.05) / (0.40 - 0.05))
                }
                d["landmarks_confidence"] = r4(Double(L.confidence))
                if let geom = faceGeometry(L, imgSize: imgSize, faceH: fbox.height * imgSize.height) { d["geom"] = geom }
            }
            d["mouth_open"] = r4(mouthOpen)
            if let eyeRatio { d["eye_ratio"] = r4(eyeRatio) }

            // Nitidezza del volto (box in pixel del crop, origine in alto).
            let pxRect = CGRect(x: fbox.minX * imgSize.width, y: (1 - fbox.maxY) * imgSize.height,
                                width: fbox.width * imgSize.width, height: fbox.height * imgSize.height)
            if let s = regionSharpness(work, pxRect) { d["sharpness"] = r4(s) }

            let fp = doIdentity ? featurePrint(work, rect: pxRect) : nil
            faces.append(FaceRec(file: fi, data: d, eyeRatio: eyeRatio, print: fp,
                                 quality: max(0, qv), mouthOpen: mouthOpen, yaw: (d["yaw"] as? Double) ?? 0))
            faceList.append(d)
        }
        out["sharpness"] = r4(imageSharpness(work))
        if let a = aestheticsReq, #available(macOS 15.0, *),
           let r = (a as? VNCalculateImageAestheticsScoresRequest)?.results?.first {
            out["aesthetic"] = r4(Double(r.overallScore))
            out["is_utility"] = r.isUtility
        }
        out["faces"] = faceList  // sostituito sotto con i campi normalizzati
        results.append(out)
        logErr("[score] \(fi + 1)/\(files.count) \(URL(fileURLWithPath: path).lastPathComponent): \(lmObs.count) volti")
    }

    // Identità: clustering per average-linkage sulle feature print del volto.
    let threshold = Double(args.options["id-threshold"] ?? "") ?? 0.62
    var clusters: [[Int]] = []
    for (i, f) in faces.enumerated() {
        guard let fp = f.print else { clusters.append([i]); continue }
        var best = -1, bestD = Double.greatestFiniteMagnitude
        for (ci, c) in clusters.enumerated() {
            // Mai due volti della stessa immagine nella stessa persona.
            if c.contains(where: { faces[$0].file == f.file }) { continue }
            var tot = 0.0, n = 0.0
            for j in c { if let other = faces[j].print {
                var dist: Float = 0
                if (try? fp.computeDistance(&dist, to: other)) != nil { tot += Double(dist); n += 1 }
            } }
            if n > 0, tot / n < bestD { bestD = tot / n; best = ci }
        }
        if debug { logErr("[id] volto \(i) file \(f.file): cluster più vicino \(best) d=\(r4(bestD))") }
        if best >= 0, bestD < threshold { clusters[best].append(i) } else { clusters.append([i]) }
    }

    // Normalizzazione per persona di occhi aperti (rapporto rispetto al p80 della persona + z-score robusto).
    var personOf = [Int](repeating: 0, count: faces.count)
    for (ci, c) in clusters.enumerated() { for i in c { personOf[i] = ci } }
    var normEyes = [Double?](repeating: nil, count: faces.count)
    var zEyes = [Double?](repeating: nil, count: faces.count)
    var normMode = [String](repeating: "absolute", count: faces.count)
    for c in clusters {
        let vals = c.compactMap { faces[$0].eyeRatio }.sorted()
        for i in c {
            guard let r = faces[i].eyeRatio else { continue }
            if vals.count >= 3 {
                let p80 = vals[min(vals.count - 1, Int((Double(vals.count - 1) * 0.8).rounded()))]
                let med = vals[vals.count / 2]
                let mad = vals.map { abs($0 - med) }.sorted()[vals.count / 2] * 1.4826
                normEyes[i] = clamp01((r / max(p80, 1e-6) - 0.45) / (0.85 - 0.45))
                zEyes[i] = mad > 1e-6 ? (r - med) / mad : 0
                normMode[i] = "person"
            } else {
                normEyes[i] = eyesAbsolute(r)
            }
        }
    }

    // Riscrive i volti con i campi finali e il punteggio di scelta.
    var perFile: [Int: [[String: Any]]] = [:]
    for (i, f) in faces.enumerated() {
        var d = f.data
        let eyes = normEyes[i] ?? 0.5
        d["eyes_open"] = normEyes[i].map { r4($0) } ?? NSNull()
        d["eyes_norm"] = normEyes[i] == nil ? "none" : normMode[i]
        if let z = zEyes[i] { d["eyes_z"] = r4(z) }
        d["person"] = "P\(personOf[i] + 1)"
        // Punteggio euristico per ordinare i candidati (non un predittore di CTR):
        // qualità × occhi aperti × bocca non a metà parola × volto frontale.
        let frontal = cos(min(abs(f.yaw), 90) * .pi / 180)
        let pick = f.quality * (0.35 + 0.65 * eyes) * (1 - 0.3 * f.mouthOpen) * (0.7 + 0.3 * frontal)
        d["pick"] = r4(pick)
        perFile[f.file, default: []].append(d)
    }
    for fi in 0..<results.count {
        let list = perFile[fi] ?? []
        results[fi]["faces"] = list
        let qs = list.compactMap { $0["quality"] as? Double }
        results[fi]["best_face_quality"] = qs.max().map { r4($0) } ?? NSNull()
        results[fi]["best_pick"] = list.compactMap { $0["pick"] as? Double }.max().map { r4($0) } ?? NSNull()
    }
    printJSON(results)
}

// MARK: - faces (box per reframing)

func cmdFaces(_ args: Args) {
    let files = expandInputs(args)
    if files.isEmpty { die("faces: nessuna immagine", code: 64) }
    let wantBodies = args.flags.contains("bodies")
    var results: [[String: Any]] = []
    for (fi, path) in files.enumerated() {
        var out: [String: Any] = ["file": path]
        guard let full = loadImage(path) else { out["error"] = "impossibile leggere l'immagine"; out["faces"] = [Any](); results.append(out); continue }
        let fullW = full.width, fullH = full.height
        var crop = CGRect(x: 0, y: 0, width: fullW, height: fullH)
        if let roiS = args.options["roi"] {
            guard let r = parseRect(roiS, width: fullW, height: fullH) else { die("--roi non valida: \(roiS)", code: 64) }
            crop = r
        }
        guard let work = (crop.size == CGSize(width: fullW, height: fullH)) ? full : full.cropping(to: crop) else { continue }
        let handler = VNImageRequestHandler(cgImage: work, options: [:])
        let faceReq = VNDetectFaceRectanglesRequest()
        var reqs: [VNRequest] = [faceReq]
        let bodyReq = VNDetectHumanRectanglesRequest()
        bodyReq.upperBodyOnly = false
        if wantBodies { reqs.append(bodyReq) }
        do { try handler.perform(reqs) } catch { out["error"] = "vision: \(error.localizedDescription)"; results.append(out); continue }
        out["w"] = fullW; out["h"] = fullH
        var fl: [[String: Any]] = []
        for f in (faceReq.results ?? []).sorted(by: { $0.boundingBox.minX < $1.boundingBox.minX }) {
            var d: [String: Any] = ["box": toFullNorm(f.boundingBox, crop: crop, fullW: fullW, fullH: fullH),
                                    "confidence": r4(Double(f.confidence)),
                                    "face_px": Int((f.boundingBox.height * crop.height).rounded())]
            if let yaw = f.yaw { d["yaw"] = r4(yaw.doubleValue * 180 / .pi) }
            if let roll = f.roll { d["roll"] = r4(roll.doubleValue * 180 / .pi) }
            fl.append(d)
        }
        out["faces"] = fl
        if wantBodies {
            out["bodies"] = (bodyReq.results ?? []).sorted(by: { $0.boundingBox.minX < $1.boundingBox.minX }).map {
                ["box": toFullNorm($0.boundingBox, crop: crop, fullW: fullW, fullH: fullH), "confidence": r4(Double($0.confidence))] as [String: Any]
            }
        }
        results.append(out)
        if files.count > 20, fi % 50 == 0 { logErr("[faces] \(fi + 1)/\(files.count)") }
    }
    printJSON(results)
}

// MARK: - cutout

/// Etichette dell'instanceMask (bassa risoluzione, UInt8, riga 0 = alto) → statistiche per istanza.
struct InstanceStat { var label: Int; var pixels: Int; var cx: Double; var cy: Double; var box: [Double] }

func instanceStats(_ obs: VNInstanceMaskObservation) -> (stats: [InstanceStat], lookup: (CGPoint) -> Int) {
    let pb = obs.instanceMask
    CVPixelBufferLockBaseAddress(pb, .readOnly)
    defer { CVPixelBufferUnlockBaseAddress(pb, .readOnly) }
    let w = CVPixelBufferGetWidth(pb), h = CVPixelBufferGetHeight(pb), bpr = CVPixelBufferGetBytesPerRow(pb)
    let base = CVPixelBufferGetBaseAddress(pb)!.assumingMemoryBound(to: UInt8.self)
    var labels = [UInt8](repeating: 0, count: w * h)
    var acc: [Int: (n: Int, sx: Double, sy: Double, x0: Int, y0: Int, x1: Int, y1: Int)] = [:]
    for y in 0..<h {
        for x in 0..<w {
            let v = base[y * bpr + x]
            labels[y * w + x] = v
            if v == 0 { continue }
            var a = acc[Int(v)] ?? (0, 0, 0, x, y, x, y)
            a.n += 1; a.sx += Double(x); a.sy += Double(y)
            a.x0 = min(a.x0, x); a.y0 = min(a.y0, y); a.x1 = max(a.x1, x); a.y1 = max(a.y1, y)
            acc[Int(v)] = a
        }
    }
    let stats = acc.keys.sorted().map { k -> InstanceStat in
        let a = acc[k]!
        return InstanceStat(label: k, pixels: a.n, cx: a.sx / Double(a.n) / Double(w), cy: a.sy / Double(a.n) / Double(h),
                            box: [r4(Double(a.x0) / Double(w)), r4(Double(a.y0) / Double(h)),
                                  r4(Double(a.x1 - a.x0 + 1) / Double(w)), r4(Double(a.y1 - a.y0 + 1) / Double(h))])
    }
    let lookup: (CGPoint) -> Int = { p in
        let x = min(w - 1, max(0, Int(p.x * Double(w)))), y = min(h - 1, max(0, Int(p.y * Double(h))))
        return Int(labels[y * w + x])
    }
    return (stats, lookup)
}

/// Rende una maschera CIImage (grigio) in un buffer 8 bit della dimensione data.
func renderMask(_ ctx: CIContext, _ img: CIImage, width: Int, height: Int) -> [UInt8] {
    var buf = [UInt8](repeating: 0, count: width * height)
    buf.withUnsafeMutableBytes { raw in
        ctx.render(img, toBitmap: raw.baseAddress!, rowBytes: width, bounds: CGRect(x: 0, y: 0, width: width, height: height),
                   format: .L8, colorSpace: nil)
    }
    return buf  // riga 0 = ALTO (render su bitmap: righe dall'alto)
}

/// Componenti connesse (4-vicini) della maschera binaria (>127): tiene quelle con area ≥ minFrac della
/// più grande. Ritorna la maschera 0/255 delle componenti tenute e il numero di isole scartate.
func mainComponents(_ m: [UInt8], _ W: Int, _ H: Int, minFrac: Double) -> ([UInt8], Int) {
    var label = [Int32](repeating: 0, count: W * H)
    var areas: [Int] = [0]
    var stack: [Int] = []
    stack.reserveCapacity(1 << 16)
    var next: Int32 = 1
    for start in 0..<(W * H) where m[start] > 127 && label[start] == 0 {
        var area = 0
        label[start] = next; stack.append(start)
        while let p = stack.popLast() {
            area += 1
            let x = p % W, y = p / W
            if x > 0, m[p - 1] > 127, label[p - 1] == 0 { label[p - 1] = next; stack.append(p - 1) }
            if x < W - 1, m[p + 1] > 127, label[p + 1] == 0 { label[p + 1] = next; stack.append(p + 1) }
            if y > 0, m[p - W] > 127, label[p - W] == 0 { label[p - W] = next; stack.append(p - W) }
            if y < H - 1, m[p + W] > 127, label[p + W] == 0 { label[p + W] = next; stack.append(p + W) }
        }
        areas.append(area); next += 1
    }
    let biggest = areas.max() ?? 0
    let keepLabel = areas.map { Double($0) >= Double(biggest) * minFrac && $0 > 0 }
    var out = [UInt8](repeating: 0, count: W * H)
    for i in 0..<(W * H) where label[i] > 0 && keepLabel[Int(label[i])] { out[i] = 255 }
    return (out, keepLabel.dropFirst().filter { !$0 }.count)
}

func cmdCutout(_ args: Args) {
    guard let inPath = args.positional.first else { die("cutout: manca IMG (usa: thumbvision cutout IMG --out PNG)", code: 64) }
    guard let outPath = args.options["out"] ?? (args.positional.count > 1 ? args.positional[1] : nil) else { die("cutout: manca --out PNG", code: 64) }
    let mode = args.options["mode"] ?? "person"
    guard ["person", "subject"].contains(mode) else { die("--mode deve essere person|subject", code: 64) }
    let instanceSel = args.options["instance"] ?? "auto"
    let matte = args.options["matte"] ?? "auto"
    let feather = Double(args.options["feather"] ?? "") ?? 1.5
    let choke = Double(args.options["choke"] ?? "") ?? 0
    let pad = Int(args.options["pad"] ?? "") ?? 24

    guard let full = loadImage(inPath) else { die("impossibile leggere l'immagine: \(inPath)") }
    let fullW = full.width, fullH = full.height
    var crop = CGRect(x: 0, y: 0, width: fullW, height: fullH)
    if let roiS = args.options["roi"] {
        guard let r = parseRect(roiS, width: fullW, height: fullH) else { die("--roi non valida: \(roiS)", code: 64) }
        crop = r
    }
    guard let work = (crop.size == CGSize(width: fullW, height: fullH)) ? full : full.cropping(to: crop) else { die("crop fallito") }
    let W = work.width, H = work.height
    let handler = VNImageRequestHandler(cgImage: work, options: [:])
    let ctx = CIContext(options: [.workingColorSpace: CGColorSpace(name: CGColorSpace.sRGB)!])
    var summary: [String: Any] = ["ok": true, "input": inPath, "mode": mode,
                                  "roi_px": [Int(crop.minX), Int(crop.minY), W, H]]

    // Punto di selezione (normalizzato all'immagine intera) → coordinate del crop.
    var selPoint: CGPoint? = nil
    if let ps = args.options["point"] {
        guard let p = parsePoint(ps) else { die("--point non valido: \(ps)", code: 64) }
        selPoint = CGPoint(x: (p.x * Double(fullW) - crop.minX) / crop.width, y: (p.y * Double(fullH) - crop.minY) / crop.height)
    }

    // 1) Maschera d'istanza (persona o soggetto) e scelta delle istanze da tenere.
    let instReq: VNImageBasedRequest = mode == "person" ? VNGeneratePersonInstanceMaskRequest() : VNGenerateForegroundInstanceMaskRequest()
    do { try handler.perform([instReq]) } catch { die("vision: \(error.localizedDescription)") }
    let instObs = (instReq.results as? [VNInstanceMaskObservation])?.first
    var mask: CIImage
    var selectedLabels: [Int] = []
    var instancesInfo: [[String: Any]] = []
    if let obs = instObs, !obs.allInstances.isEmpty {
        let (stats, lookup) = instanceStats(obs)
        instancesInfo = stats.map { ["label": $0.label, "area": r4(Double($0.pixels) / Double(CVPixelBufferGetWidth(obs.instanceMask) * CVPixelBufferGetHeight(obs.instanceMask))), "box_in_roi": $0.box] }
        var sel = IndexSet()
        if let p = selPoint {
            let l = lookup(p)
            if l > 0 { sel.insert(l) } else {
                // Nessuna istanza sotto il punto: la più vicina per centroide.
                if let s = stats.min(by: { hypot($0.cx - p.x, $0.cy - p.y) < hypot($1.cx - p.x, $1.cy - p.y) }) { sel.insert(s.label) }
            }
        } else {
            switch instanceSel {
            case "all": sel = obs.allInstances
            case "center":
                if let s = stats.min(by: { hypot($0.cx - 0.5, $0.cy - 0.5) < hypot($1.cx - 0.5, $1.cy - 0.5) }) { sel.insert(s.label) }
            case "largest":
                if let s = stats.max(by: { $0.pixels < $1.pixels }) { sel.insert(s.label) }
            case "auto":
                // Persona: la più grande; soggetto: tutto il primo piano (microfoni, cuffie inclusi).
                if mode == "person", let s = stats.max(by: { $0.pixels < $1.pixels }) { sel.insert(s.label) } else { sel = obs.allInstances }
            default:
                for part in instanceSel.split(separator: ",") { if let n = Int(part), obs.allInstances.contains(n) { sel.insert(n) } }
                if sel.isEmpty { die("--instance \(instanceSel): nessuna istanza valida (disponibili: \(Array(obs.allInstances)))", code: 65) }
            }
        }
        selectedLabels = Array(sel)
        do {
            let pb = try obs.generateScaledMaskForImage(forInstances: sel, from: handler)
            mask = CIImage(cvPixelBuffer: pb)
        } catch { die("maschera d'istanza fallita: \(error.localizedDescription)") }
        summary["instance_mask_px"] = [CVPixelBufferGetWidth(obs.instanceMask), CVPixelBufferGetHeight(obs.instanceMask)]
    } else if mode == "person" {
        // Nessuna istanza: ripiego sulla segmentazione persona (tutte le persone insieme).
        logErr("[cutout] nessuna istanza persona: uso VNGeneratePersonSegmentationRequest")
        mask = CIImage(color: .white).cropped(to: CGRect(x: 0, y: 0, width: W, height: H))
        summary["warning"] = "nessuna istanza persona trovata: maschera dalla sola segmentazione"
    } else {
        die("nessun soggetto trovato", code: 2)
    }
    summary["instances"] = instancesInfo
    summary["selected"] = selectedLabels

    // 2) Matte accurato (solo persone): bordi più fini, intersecato con l'istanza scelta dilatata.
    var matteUsed = "instance"
    if mode == "person" && matte != "instance" {
        let seg = VNGeneratePersonSegmentationRequest()
        seg.qualityLevel = .accurate
        seg.outputPixelFormat = kCVPixelFormatType_OneComponent8
        if (try? handler.perform([seg])) != nil, let pb = seg.results?.first?.pixelBuffer {
            let mw = CVPixelBufferGetWidth(pb), mh = CVPixelBufferGetHeight(pb)
            let segImg = CIImage(cvPixelBuffer: pb)
                .transformed(by: CGAffineTransform(scaleX: CGFloat(W) / CGFloat(mw), y: CGFloat(H) / CGFloat(mh)))
            // Istanza binarizzata (niente "fantasmi" a bassa confidenza delle persone vicine), poi dilatata
            // (~0.8% del lato) per non tagliare i capelli che il matte accurato vede.
            let r = max(4.0, Double(max(W, H)) * 0.008)
            let bin = mask.applyingFilter("CIColorThreshold", parameters: ["inputThreshold": 0.5]).cropped(to: mask.extent)
            let dil = bin.applyingFilter("CIMorphologyMaximum", parameters: ["inputRadius": r]).cropped(to: mask.extent)
            mask = segImg.applyingFilter("CIMinimumCompositing", parameters: [kCIInputBackgroundImageKey: dil])
                .cropped(to: CGRect(x: 0, y: 0, width: W, height: H))
            matteUsed = "accurate"
            summary["matte_px"] = [mw, mh]
        } else if matte == "accurate" {
            die("segmentazione persona accurata non disponibile")
        }
    }
    summary["matte"] = matteUsed

    // 3) Rifinitura bordo: choke (erosione) contro l'alone del muro arancione, poi feather.
    if choke > 0 {
        mask = mask.applyingFilter("CIMorphologyMinimum", parameters: ["inputRadius": choke]).cropped(to: CGRect(x: 0, y: 0, width: W, height: H))
    }
    if feather > 0 {
        mask = mask.clampedToExtent().applyingFilter("CIGaussianBlur", parameters: ["inputRadius": feather / 2])
            .cropped(to: CGRect(x: 0, y: 0, width: W, height: H))
    }
    summary["feather"] = feather; summary["choke"] = choke

    // 3b) Zone escluse (es. PiP di un layout composito appoggiato sulla testa): maschera azzerata lì dentro.
    if let ex = args.options["exclude"] {
        var keepAll = CIImage(color: CIColor(red: 1, green: 1, blue: 1)).cropped(to: CGRect(x: 0, y: 0, width: W, height: H))
        var used: [[Int]] = []
        for part in ex.split(separator: ";") {
            guard let r = parseRect(String(part), width: fullW, height: fullH) else { die("--exclude non valida: \(part)", code: 64) }
            let rc = r.intersection(crop)
            if rc.isNull || rc.isEmpty { continue }
            // crop (origine in alto) → coordinate CoreImage del crop (origine in basso)
            let ci = CGRect(x: rc.minX - crop.minX, y: crop.maxY - rc.maxY, width: rc.width, height: rc.height)
            keepAll = CIImage(color: CIColor(red: 0, green: 0, blue: 0)).cropped(to: ci).composited(over: keepAll)
            used.append([Int(rc.minX), Int(rc.minY), Int(rc.width), Int(rc.height)])
        }
        mask = mask.applyingFilter("CIMultiplyCompositing", parameters: [kCIInputBackgroundImageKey: keepAll])
            .cropped(to: CGRect(x: 0, y: 0, width: W, height: H))
        summary["excluded_px"] = used
    }

    // 4) Isole: si tengono solo le componenti connesse principali (via oggetti staccati e
    //    aloni semitrasparenti di altre persone); il resto della maschera viene azzerato.
    let full1 = CGRect(x: 0, y: 0, width: W, height: H)
    var m8 = renderMask(ctx, mask, width: W, height: H)
    let (keep, removed) = mainComponents(m8, W, H, minFrac: Double(args.options["min-island"] ?? "") ?? 0.08)
    if removed > 0 {
        let keepImg = CIImage(bitmapData: Data(keep), bytesPerRow: W, size: CGSize(width: W, height: H), format: .L8, colorSpace: nil)
        let grow = keepImg.applyingFilter("CIMorphologyMaximum", parameters: ["inputRadius": max(3.0, feather + 2)]).cropped(to: full1)
            .clampedToExtent().applyingFilter("CIGaussianBlur", parameters: ["inputRadius": 1.0]).cropped(to: full1)
        mask = mask.applyingFilter("CIMultiplyCompositing", parameters: [kCIInputBackgroundImageKey: grow]).cropped(to: full1)
        m8 = renderMask(ctx, mask, width: W, height: H)
    }
    summary["islands_removed"] = removed

    // 5) Metriche sul bordo dalla maschera finale (8 bit, riga 0 = alto).
    var opaque = 0, soft = 0, boundary = 0
    var x0 = W, y0 = H, x1 = -1, y1 = -1
    for y in 0..<H {
        let row = y * W
        for x in 0..<W {
            let a = m8[row + x]
            if a > 127 {
                opaque += 1
                x0 = min(x0, x); x1 = max(x1, x); y0 = min(y0, y); y1 = max(y1, y)
                if x > 0, x < W - 1, y > 0, y < H - 1,
                   m8[row + x - 1] <= 127 || m8[row + x + 1] <= 127 || m8[row + x - W] <= 127 || m8[row + x + W] <= 127 {
                    boundary += 1
                }
            }
            if a > 12 && a < 243 { soft += 1 }
        }
    }
    if opaque == 0 { die("maschera vuota: nessuna persona/soggetto selezionato", code: 2) }
    summary["coverage"] = r4(Double(opaque) / Double(W * H))
    summary["edge_px"] = boundary
    summary["edge_softness_px"] = r4(Double(soft) / Double(max(boundary, 1)))  // larghezza media della transizione
    let bboxFull = [r4((crop.minX + CGFloat(x0)) / CGFloat(fullW)), r4((crop.minY + CGFloat(y0)) / CGFloat(fullH)),
                    r4(CGFloat(x1 - x0 + 1) / CGFloat(fullW)), r4(CGFloat(y1 - y0 + 1) / CGFloat(fullH))]
    summary["alpha_box"] = bboxFull
    // Tocca il bordo del crop? (persona tagliata dal riquadro → in template va ancorata a quel lato)
    summary["touches"] = ["left": x0 <= 1, "right": x1 >= W - 2, "top": y0 <= 1, "bottom": y1 >= H - 2]

    // 6) Decontaminazione colore del bordo: nella fascia di transizione il colore del fondo
    //    (es. un muro arancione) "sporca" capelli e spalle. Lo sostituiamo con il colore stimato
    //    dall'interno del soggetto: media pesata blur(src·interno)/blur(interno).
    let full0 = CGRect(x: 0, y: 0, width: W, height: H)
    var src = CIImage(cgImage: work)
    let decontam = Double(args.options["decontam"] ?? "") ?? 6
    if decontam > 0 {
        let inner = mask.applyingFilter("CIMorphologyMinimum", parameters: ["inputRadius": decontam]).cropped(to: full0)
        let sigma = decontam * 1.5
        let num = src.applyingFilter("CIMultiplyCompositing", parameters: [kCIInputBackgroundImageKey: inner])
            .clampedToExtent().applyingFilter("CIGaussianBlur", parameters: ["inputRadius": sigma]).cropped(to: full0)
        let den = inner.clampedToExtent().applyingFilter("CIGaussianBlur", parameters: ["inputRadius": sigma]).cropped(to: full0)
            .applyingFilter("CIColorMatrix", parameters: ["inputBiasVector": CIVector(x: 0.002, y: 0.002, z: 0.002, w: 0)])
        // CIDivideBlendMode: risultato = background / input.
        let est = den.applyingFilter("CIDivideBlendMode", parameters: [kCIInputBackgroundImageKey: num]).cropped(to: full0)
        let innerSoft = inner.clampedToExtent().applyingFilter("CIGaussianBlur", parameters: ["inputRadius": 1.5]).cropped(to: full0)
        // fascia = 1 dove NON siamo nell'interno: lì prende il colore stimato.
        src = src.applyingFilter("CIBlendWithMask", parameters: [kCIInputBackgroundImageKey: est, kCIInputMaskImageKey: innerSoft])
            .cropped(to: full0)
    }
    summary["decontam"] = decontam

    // 7) Composito RGBA (alpha dritto nel PNG) ed eventuale trim.
    var outImg = src.applyingFilter("CIBlendWithMask", parameters: [
        kCIInputBackgroundImageKey: CIImage.empty(), kCIInputMaskImageKey: mask])
        .cropped(to: CGRect(x: 0, y: 0, width: W, height: H))
    var maskOut = mask
    var outRectPx = CGRect(x: 0, y: 0, width: W, height: H)  // origine in alto, coordinate del crop
    if args.flags.contains("trim") {
        let tx0 = max(0, x0 - pad), ty0 = max(0, y0 - pad), tx1 = min(W - 1, x1 + pad), ty1 = min(H - 1, y1 + pad)
        outRectPx = CGRect(x: tx0, y: ty0, width: tx1 - tx0 + 1, height: ty1 - ty0 + 1)
        let ciRect = CGRect(x: CGFloat(tx0), y: CGFloat(H - 1 - ty1), width: outRectPx.width, height: outRectPx.height)
        let shift = CGAffineTransform(translationX: -ciRect.minX, y: -ciRect.minY)
        outImg = outImg.cropped(to: ciRect).transformed(by: shift)
        maskOut = maskOut.cropped(to: ciRect).transformed(by: shift)
    }
    let srgb = CGColorSpace(name: CGColorSpace.sRGB)!
    do {
        try FileManager.default.createDirectory(at: URL(fileURLWithPath: outPath).deletingLastPathComponent(), withIntermediateDirectories: true)
        try ctx.writePNGRepresentation(of: outImg, to: URL(fileURLWithPath: outPath), format: .RGBA8, colorSpace: srgb)
        if let mp = args.options["mask-out"] {
            try ctx.writePNGRepresentation(of: maskOut, to: URL(fileURLWithPath: mp), format: .L8, colorSpace: CGColorSpace(name: CGColorSpace.linearGray)!)
            summary["mask"] = mp
        }
    } catch { die("scrittura PNG fallita: \(error.localizedDescription)") }
    summary["out"] = outPath
    summary["out_px"] = [Int(outRectPx.width), Int(outRectPx.height)]
    // Posizione dell'output nell'immagine intera (per riposizionare il ritaglio sul frame originale).
    summary["out_box"] = [r4((crop.minX + outRectPx.minX) / CGFloat(fullW)), r4((crop.minY + outRectPx.minY) / CGFloat(fullH)),
                          r4(outRectPx.width / CGFloat(fullW)), r4(outRectPx.height / CGFloat(fullH))]
    printJSON(summary)
}

// MARK: - saliency (QA: cosa si nota per primo)

/// Box nominati "nome:x,y,w,h;nome2:…" (normalizzati se tutti ≤1, altrimenti pixel; origine in alto a sinistra).
func parseNamedBoxes(_ s: String, width: Int, height: Int) -> [(String, CGRect)] {
    var out: [(String, CGRect)] = []
    for part in s.split(separator: ";") {
        let kv = part.split(separator: ":", maxSplits: 1).map(String.init)
        guard kv.count == 2, let r = parseRect(kv[1], width: width, height: height) else {
            die("--boxes non valida: \(part) (usa nome:x,y,w,h;…)", code: 64)
        }
        out.append((kv[0].trimmingCharacters(in: .whitespaces), r))
    }
    return out
}

/// Colore della heatmap (inchiostro → arancio → giallo), t in 0–1.
func heatColour(_ t: Double) -> (Double, Double, Double) {
    let stops: [(Double, Double, Double, Double)] = [(0, 0.12, 0.11, 0.11), (0.5, 0.97, 0.34, 0.0), (1, 0.94, 0.77, 0.28)]
    let x = clamp01(t)
    for i in 1..<stops.count where x <= stops[i].0 {
        let a = stops[i - 1], b = stops[i], k = (x - a.0) / (b.0 - a.0)
        return (a.1 + (b.1 - a.1) * k, a.2 + (b.2 - a.2) * k, a.3 + (b.3 - a.3) * k)
    }
    return (stops.last!.1, stops.last!.2, stops.last!.3)
}

func cmdSaliency(_ args: Args) {
    let files = expandInputs(args)
    if files.isEmpty { die("saliency: nessuna immagine (usa: thumbvision saliency IMG [--out PNG] [--boxes nome:x,y,w,h;…])", code: 64) }
    let mode = args.options["mode"] ?? "attention"
    guard ["attention", "objectness"].contains(mode) else { die("--mode deve essere attention|objectness", code: 64) }
    if args.options["out"] != nil && files.count > 1 { die("--out vale per una sola immagine: con più immagini usa --out-dir", code: 64) }
    let overlay = args.flags.contains("overlay")
    var results: [[String: Any]] = []
    for path in files {
        var out: [String: Any] = ["file": path, "mode": mode]
        guard let cg = loadImage(path) else { out["error"] = "impossibile leggere l'immagine"; results.append(out); continue }
        let W = cg.width, H = cg.height
        out["w"] = W; out["h"] = H
        let req: VNImageBasedRequest = mode == "attention" ? VNGenerateAttentionBasedSaliencyImageRequest() : VNGenerateObjectnessBasedSaliencyImageRequest()
        do { try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req]) } catch {
            out["error"] = "vision: \(error.localizedDescription)"; results.append(out); continue
        }
        guard let obs = req.results?.first as? VNSaliencyImageObservation else { out["error"] = "nessun risultato"; results.append(out); continue }
        let pb = obs.pixelBuffer
        CVPixelBufferLockBaseAddress(pb, .readOnly)
        let gw = CVPixelBufferGetWidth(pb), gh = CVPixelBufferGetHeight(pb), bpr = CVPixelBufferGetBytesPerRow(pb)
        let fmt = CVPixelBufferGetPixelFormatType(pb)
        var grid = [Double](repeating: 0, count: gw * gh)   // riga 0 = alto (buffer Vision: righe dall'alto)
        if let base = CVPixelBufferGetBaseAddress(pb) {
            for y in 0..<gh {
                for x in 0..<gw {
                    if fmt == kCVPixelFormatType_OneComponent32Float {
                        grid[y * gw + x] = Double(base.advanced(by: y * bpr).assumingMemoryBound(to: Float32.self)[x])
                    } else {
                        grid[y * gw + x] = Double(base.advanced(by: y * bpr).assumingMemoryBound(to: UInt8.self)[x]) / 255
                    }
                }
            }
        }
        CVPixelBufferUnlockBaseAddress(pb, .readOnly)
        let mx = max(grid.max() ?? 0, 1e-9)
        grid = grid.map { max(0, $0) / mx }
        let total = max(grid.reduce(0, +), 1e-9)
        var px = 0, sx = 0.0, sy = 0.0
        for i in 0..<grid.count {
            if grid[i] > grid[px] { px = i }
            sx += grid[i] * (Double(i % gw) + 0.5); sy += grid[i] * (Double(i / gw) + 0.5)
        }
        out["heat_px"] = [gw, gh]
        out["peak"] = [r4((Double(px % gw) + 0.5) / Double(gw)), r4((Double(px / gw) + 0.5) / Double(gh))]
        out["centroid"] = [r4(sx / total / Double(gw)), r4(sy / total / Double(gh))]
        // regione principale: box dei salientObjects di Vision (origine in basso → in alto)
        let objs = (obs.salientObjects ?? []).sorted(by: { $0.confidence > $1.confidence }).map { o -> [String: Any] in
            let b = o.boundingBox
            return ["box": [r4(b.minX), r4(1 - b.maxY), r4(b.width), r4(b.height)], "confidence": r4(Double(o.confidence))]
        }
        out["objects"] = objs
        // e, indipendente, il box delle celle ≥ 50% del massimo
        var x0 = gw, y0 = gh, x1 = -1, y1 = -1
        for i in 0..<grid.count where grid[i] >= 0.5 {
            let x = i % gw, y = i / gw
            x0 = min(x0, x); x1 = max(x1, x); y0 = min(y0, y); y1 = max(y1, y)
        }
        if x1 >= 0 {
            out["top_region"] = [r4(Double(x0) / Double(gw)), r4(Double(y0) / Double(gh)),
                                 r4(Double(x1 - x0 + 1) / Double(gw)), r4(Double(y1 - y0 + 1) / Double(gh))]
        }
        // quota di salienza dentro i box nominati (es. volto, frase): chi vince si nota per primo
        func sample(_ u: Double, _ v: Double) -> Double {   // bilineare, u/v in 0–1 (origine in alto)
            let fx = min(max(u * Double(gw) - 0.5, 0), Double(gw - 1)), fy = min(max(v * Double(gh) - 0.5, 0), Double(gh - 1))
            let ix = Int(fx), iy = Int(fy), jx = min(ix + 1, gw - 1), jy = min(iy + 1, gh - 1)
            let ax = fx - Double(ix), ay = fy - Double(iy)
            let top = grid[iy * gw + ix] * (1 - ax) + grid[iy * gw + jx] * ax
            let bot = grid[jy * gw + ix] * (1 - ax) + grid[jy * gw + jx] * ax
            return top * (1 - ay) + bot * ay
        }
        if let bs = args.options["boxes"] {
            var named: [String: Any] = [:]
            var best = "", bestMean = -1.0
            for (name, r) in parseNamedBoxes(bs, width: W, height: H) {
                var acc = 0.0, peak = 0.0, n = 0.0
                let steps = 24
                for j in 0..<steps {
                    for i in 0..<steps {
                        let s = sample((Double(r.minX) + (Double(i) + 0.5) / Double(steps) * Double(r.width)) / Double(W),
                                       (Double(r.minY) + (Double(j) + 0.5) / Double(steps) * Double(r.height)) / Double(H))
                        acc += s; peak = max(peak, s); n += 1
                    }
                }
                // quota della massa totale dentro il box (celle della griglia il cui centro cade nel box)
                var inside = 0.0
                for k in 0..<grid.count {
                    let cx = (Double(k % gw) + 0.5) / Double(gw) * Double(W), cy = (Double(k / gw) + 0.5) / Double(gh) * Double(H)
                    if r.contains(CGPoint(x: cx, y: cy)) { inside += grid[k] }
                }
                let mean = acc / max(n, 1)
                named[name] = ["mean": r4(mean), "max": r4(peak), "share": r4(inside / total),
                               "box": [r4(Double(r.minX) / Double(W)), r4(Double(r.minY) / Double(H)), r4(Double(r.width) / Double(W)), r4(Double(r.height) / Double(H))]]
                if mean > bestMean { bestMean = mean; best = name }
            }
            out["boxes"] = named
            if !best.isEmpty { out["first"] = best }
        }
        // heatmap PNG (larghezza ≤ 1280): sola mappa, oppure sovrapposta all'immagine in grigio
        var heatPath: String? = args.options["out"]
        if heatPath == nil, let dir = args.options["out-dir"] {
            heatPath = URL(fileURLWithPath: dir).appendingPathComponent(URL(fileURLWithPath: path).deletingPathExtension().lastPathComponent + "_saliency.png").path
        }
        if let hp = heatPath {
            let ow = min(W, 1280), oh = max(1, Int((Double(H) * Double(ow) / Double(W)).rounded()))
            let gray = grayBuffer(cg, width: ow, height: oh)
            var rgba = [UInt8](repeating: 255, count: ow * oh * 4)
            for y in 0..<oh {
                for x in 0..<ow {
                    let h = sample((Double(x) + 0.5) / Double(ow), (Double(y) + 0.5) / Double(oh))
                    let (r, g, b) = heatColour(h)
                    let i = (y * ow + x) * 4
                    if overlay {
                        let base = Double(gray[y * ow + x]) / 255 * 0.55
                        let a = 0.25 + 0.6 * h
                        rgba[i] = UInt8(clamp01(base * (1 - a) + r * a) * 255)
                        rgba[i + 1] = UInt8(clamp01(base * (1 - a) + g * a) * 255)
                        rgba[i + 2] = UInt8(clamp01(base * (1 - a) + b * a) * 255)
                    } else {
                        rgba[i] = UInt8(r * 255); rgba[i + 1] = UInt8(g * 255); rgba[i + 2] = UInt8(b * 255)
                    }
                }
            }
            let srgb = CGColorSpace(name: CGColorSpace.sRGB)!
            let ok: Bool = rgba.withUnsafeMutableBytes { raw -> Bool in
                guard let ctx = CGContext(data: raw.baseAddress, width: ow, height: oh, bitsPerComponent: 8, bytesPerRow: ow * 4,
                                          space: srgb, bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue),
                      let img = ctx.makeImage(),
                      let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: hp) as CFURL, UTType.png.identifier as CFString, 1, nil)
                else { return false }
                try? FileManager.default.createDirectory(at: URL(fileURLWithPath: hp).deletingLastPathComponent(), withIntermediateDirectories: true)
                CGImageDestinationAddImage(dest, img, nil)
                return CGImageDestinationFinalize(dest)
            }
            if ok { out["heatmap"] = hp } else { out["heatmap_error"] = "scrittura PNG fallita: \(hp)" }
        }
        results.append(out)
    }
    printJSON(files.count == 1 ? results[0] : results)
}

// MARK: - main

let usage = """
thumbvision \(VERSION) — Apple Vision per thumbnail (on-device, nessuna rete)
  score  IMG... [--roi x,y,w,h] [--list FILE] [--no-aesthetics] [--no-identity] [--id-threshold 0.62] [--debug]
         qualità volto, occhi aperti (normalizzati per persona sull'insieme), bocca, nitidezza, estetica
  faces  IMG... [--roi x,y,w,h] [--list FILE] [--bodies]
         solo box dei volti (e dei corpi) per il reframing 9:16
  cutout IMG --out PNG [--mode person|subject] [--instance auto|largest|center|all|N[,N]] [--point x,y]
         [--roi x,y,w,h] [--exclude x,y,w,h[;x,y,w,h]] [--matte auto|instance|accurate] [--feather PX]
         [--choke PX] [--decontam PX] [--min-island 0.08] [--trim] [--pad PX] [--mask-out PNG]
         scontorno con alpha; --roi ritaglia PRIMA (consigliato per volti piccoli, es. l'inset di un master composito)
  saliency IMG... [--list FILE] [--mode attention|objectness] [--out PNG | --out-dir DIR] [--overlay]
         [--boxes nome:x,y,w,h[;nome:x,y,w,h]]
         salienza Apple Vision (QA): heatmap, picco, regione principale, quota dentro i box (chi si nota per primo)
  version
Coordinate normalizzate 0–1 sull'immagine intera, origine in alto a sinistra.
"""

let raw = Array(CommandLine.arguments.dropFirst())
guard let sub = raw.first else { FileHandle.standardError.write(usage.data(using: .utf8)!); exit(64) }
let valued: Set<String> = ["roi", "list", "out", "mode", "instance", "point", "matte", "feather", "choke", "pad", "mask-out", "id-threshold", "decontam", "min-island", "exclude", "boxes", "out-dir"]
let parsed = Args(Array(raw.dropFirst()), valued: valued)
switch sub {
case "score": cmdScore(parsed)
case "faces": cmdFaces(parsed)
case "cutout": cmdCutout(parsed)
case "saliency": cmdSaliency(parsed)
case "version", "--version": printJSON(["ok": true, "version": VERSION])
case "-h", "--help", "help": print(usage)
default:
    FileHandle.standardError.write(usage.data(using: .utf8)!)
    exit(64)
}

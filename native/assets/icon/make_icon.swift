// Genera l'icona Dock di MacLua da una foto del logo (fondo bianco, niente alpha).
//
//   swift assets/icon/make_icon.swift <sorgente.png> <out_1024.png>
//
// 1. Trova il disegno (pixel scuri) e ne calcola il riquadro.
// 2. Lo ridisegna su una squircle bianca della griglia icone macOS
//    (824 px su canvas 1024, margine 100) con ombra morbida.
// 3. Fuori dalla forma è trasparente: niente più quadrato bianco nel Dock.
import AppKit

let args = CommandLine.arguments
guard args.count == 3,
      let src = NSImage(contentsOfFile: args[1]),
      let cg = src.cgImage(forProposedRect: nil, context: nil, hints: nil)
else {
    FileHandle.standardError.write("uso: make_icon.swift <sorgente> <out.png>\n".data(using: .utf8)!)
    exit(2)
}

// — 1. riquadro del disegno: pixel con luminanza < 50% —
let w = cg.width, h = cg.height
var px = [UInt8](repeating: 0, count: w * h * 4)
let rgb = CGColorSpaceCreateDeviceRGB()
let readCtx = CGContext(data: &px, width: w, height: h, bitsPerComponent: 8,
                        bytesPerRow: w * 4, space: rgb,
                        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
readCtx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
var minX = w, minY = h, maxX = 0, maxY = 0
for y in 0..<h {
    for x in 0..<w {
        let i = (y * w + x) * 4
        let luma = (Int(px[i]) * 299 + Int(px[i + 1]) * 587 + Int(px[i + 2]) * 114) / 1000
        if luma < 128 {
            minX = min(minX, x); maxX = max(maxX, x)
            minY = min(minY, y); maxY = max(maxY, y)
        }
    }
}
guard maxX > minX, maxY > minY else { print("nessun disegno trovato"); exit(1) }
// Pulizia della foto: rumore e bianco sporco → bianco puro, così col
// blend multiply non resta l'alone rettangolare del ritaglio.
for i in stride(from: 0, to: px.count, by: 4) {
    let luma = (Int(px[i]) * 299 + Int(px[i + 1]) * 587 + Int(px[i + 2]) * 114) / 1000
    let v: UInt8 = luma > 200 ? 255 : (luma < 60 ? 0 : UInt8(luma))
    px[i] = v; px[i + 1] = v; px[i + 2] = v
}
let clean = readCtx.makeImage()!
// Nel buffer la riga 0 è in alto, come l'origine di `cropping(to:)`.
let art = CGRect(x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1)
let crop = clean.cropping(to: art)!

// — 2. canvas 1024 con squircle 824 —
let S = 1024
let out = CGContext(data: nil, width: S, height: S, bitsPerComponent: 8, bytesPerRow: 0,
                    space: rgb, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
out.interpolationQuality = .high
let tile = CGRect(x: 100, y: 100, width: 824, height: 824)
// Raggio della griglia Apple per 824 px ≈ 185; curva continua approssimata.
let shape = CGPath(roundedRect: tile, cornerWidth: 185, cornerHeight: 185, transform: nil)

out.saveGState()
out.setShadow(offset: CGSize(width: 0, height: -10), blur: 28,
              color: CGColor(gray: 0, alpha: 0.30))
out.addPath(shape)
out.setFillColor(CGColor(gray: 1, alpha: 1))
out.fillPath()
out.restoreGState()

out.saveGState()
out.addPath(shape)
out.clip()
let grad = CGGradient(colorsSpace: rgb,
                      colors: [CGColor(gray: 1, alpha: 1), CGColor(gray: 0.93, alpha: 1)] as CFArray,
                      locations: [0, 1])!
out.drawLinearGradient(grad, start: CGPoint(x: 0, y: tile.maxY), end: CGPoint(x: 0, y: tile.minY),
                       options: [])

// — 3. disegno centrato al 76% della squircle —
let box = tile.width * 0.76
let scale = min(box / art.width, box / art.height)
let dw = art.width * scale, dh = art.height * scale
let dst = CGRect(x: tile.midX - dw / 2, y: tile.midY - dh / 2, width: dw, height: dh)
// Moltiplica: il bianco della foto sparisce sul gradiente, resta solo il nero.
out.setBlendMode(.multiply)
out.draw(crop, in: dst)
out.restoreGState()

let rep = NSBitmapImageRep(cgImage: out.makeImage()!)
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: args[2]))
print("ok \(args[2]) (disegno \(Int(art.width))x\(Int(art.height)))")

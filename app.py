import importlib, subprocess, sys
for pkg, mod in [("flask", "flask"),
                 ("Pillow", "PIL"),
                 ("qrcode", "qrcode")]:
    try:
        importlib.import_module(mod)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

from flask import Flask, render_template, request, send_from_directory, jsonify
from PIL import Image, ImageDraw, ImageFont, ImageOps
import os, math, textwrap, tempfile, uuid, random, qrcode

app = Flask(__name__)
UPLOAD_FOLDER = tempfile.mkdtemp()
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

BASE_DIR     = os.path.join(os.path.dirname(__file__), "static")
FONT_BOLD    = os.path.join(BASE_DIR, "BROWN-BOLD.ttf")
FONT_REGULAR = os.path.join(BASE_DIR, "BROWN-REGULAR.ttf")
FONT_LIGHT   = os.path.join(BASE_DIR, "BROWN-LIGHT.ttf")
LOGO_BLACK   = os.path.join(BASE_DIR, "logoBlack.png")
LOGO_WHITE   = os.path.join(BASE_DIR, "logoWhite.png")

def safe_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()

# ---------- poster generator ---------------------------------------
def make_poster(config, img_paths, out_path):
    import random, math, textwrap
    dpi = 300
    mm2inch = 1 / 25.4
    W  = int(420 * mm2inch * dpi)
    H  = int(297 * mm2inch * dpi)
    COLLAGE_H = int(W * 9 / 16)
    GAP = int(dpi * 0.1)

    canvas = Image.new("RGB", (W, H), config["bg"])
    draw   = ImageDraw.Draw(canvas)

    # ---------------------------------------------------------------
    #  stochastic rectangle‑splitting – returns a list of (x,y,w,h)
    # ---------------------------------------------------------------
    def mosaic(n, x, y, w, h):
        rects = [(x, y, w, h)]
        while len(rects) < n:
            # pick the largest rect to split
            rects.sort(key=lambda r: r[2]*r[3], reverse=True)
            rx, ry, rw, rh = rects.pop(0)

            # choose split orientation
            vert_possible = rw > 2*GAP + 50
            hori_possible = rh > 2*GAP + 50
            if not (vert_possible or hori_possible):
                rects.append((rx, ry, rw, rh))
                break

            split_vert = (vert_possible and hori_possible and random.random() < .5) or (vert_possible and not hori_possible)

            if split_vert:  # vertical
                cut = random.randint(int(rw*0.3), int(rw*0.7))
                rect1 = (rx,            ry, cut-GAP//2, rh)
                rect2 = (rx+cut+GAP//2, ry, rw-cut-GAP//2, rh)
            else:          # horizontal
                cut = random.randint(int(rh*0.3), int(rh*0.7))
                rect1 = (rx, ry,            rw, cut-GAP//2)
                rect2 = (rx, ry+cut+GAP//2, rw, rh-cut-GAP//2)

            rects.extend([rect1, rect2])
        return rects[:n]

    # ---------- build collage --------------------------------------
    n_imgs = len(img_paths)
    rects  = mosaic(n_imgs, GAP, GAP, W - 2*GAP, COLLAGE_H - GAP)

    for img_path, (x, y, w, h) in zip(img_paths, rects):
        im = Image.open(img_path).convert("RGB")
        im = ImageOps.fit(im, (w, h), Image.LANCZOS, centering=(0.5, 0.5))
        canvas.paste(im, (x, y))

    # -------------- QR ----------------------------------------
    if config["link"]:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=0
        )

        qr.add_data(config["link"])
        qr.make(fit=True)

        qr_img = qr.make_image(
            fill_color=config["fg"],
            back_color=config["bg"]
        ).convert("RGB")

        qr_size = int(dpi * 1.4)
        qr_img  = qr_img.resize((qr_size, qr_size), Image.NEAREST)

        GAP2       = GAP * 2
        inner_pad  = GAP2
        caption    = "Scan for more\nproject info"
        ft_cap     = safe_font(config["font_small"], int(dpi * 0.18))

        # calculate multiline text height
        lines     = caption.split("\n")
        line_h    = ft_cap.getbbox("Ag")[3] - ft_cap.getbbox("Ag")[1]
        cap_h     = len(lines) * line_h + int(dpi * 0.05) * (len(lines) - 1)

        box_w     = qr_size + inner_pad * 2
        box_h     = inner_pad + qr_size + inner_pad // 4 + cap_h + inner_pad

        box       = Image.new("RGB", (box_w, box_h), config["bg"])
        draw_box  = ImageDraw.Draw(box)

        # paste QR image centered horizontally
        box.paste(qr_img, (inner_pad, inner_pad))

        # draw caption centered under QR
        text_y = inner_pad + qr_size + inner_pad // 2
        draw_box.multiline_text(
            (box_w // 2, text_y),
            caption,
            font=ft_cap,
            fill=config["fg"],
            anchor="ma",
            align="center",
            spacing=int(dpi * 0.07)
        )

        canvas.paste(box, (W - box_w,0))


    # -------------- footer ----------------------------------------
    footer_y = COLLAGE_H + GAP * 2
    ft_title = safe_font(config["font_title"], int(dpi * 0.50))
    ft_body  = safe_font(config["font_body"],  int(dpi * 0.22))
    ft_small = safe_font(config["font_small"], int(dpi * 0.19))

    draw.text((GAP * 2, footer_y), config["project"], font=ft_title, fill=config["fg"])

    wrapped = "\n".join(textwrap.wrap(config["description"], width=100))
    draw.multiline_text((GAP * 2, footer_y + int(dpi * 0.55)),
                        wrapped, font=ft_body, fill=config["fg"],
                        spacing=int(dpi * 0.09))

    authors_display = ", ".join(config["authors"][:-1]) + " & " + config["authors"][-1]
    draw.multiline_text((GAP * 2, footer_y + int(dpi * 1.6)),
                        f"{config['semester']} - {config['course']}\n{authors_display}",
                        font=ft_small, fill=config["fg"],
                        spacing=int(dpi * 0.07))

    # -------------- logo ------------------------------------------
    logo = Image.open(config["logo"]).convert("RGBA")
    w0, h0 = logo.size
    max_h  = int((H - footer_y - GAP * 2) // 1.5)
    logo   = logo.resize((int(w0 * max_h / h0), max_h), Image.LANCZOS)
    lx, ly = int(W - GAP - logo.width * 1.17), int(H - GAP - logo.height * 1.3)
    canvas.paste(logo, (lx, ly), logo)

    canvas.save(out_path, dpi=(dpi, dpi))

# ---------------------- routes ---------------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate():
    img_paths = []
    for f in request.files.getlist("images"):
        fname = os.path.join(UPLOAD_FOLDER, f"{uuid.uuid4().hex}_{f.filename}")
        f.save(fname)
        img_paths.append(fname)
    random.shuffle(img_paths)

    title_raw = request.form["project_name"][:40]
    desc_raw  = request.form["description"][:290]
    selected_course = request.form.get("course", "").strip()
    custom_course   = request.form.get("course_custom", "").strip()

    cfg = {
        "project":     title_raw.title(),
        "description": desc_raw.strip().capitalize(),
        "semester":    request.form["semester"],
        "course":      (custom_course or selected_course).title(),
        "authors":     [a.strip().title() for a in request.form["authors"].split(",")],
        "bg":   ("black" if request.form.get("dark") else "white"),
        "fg":   ("white" if request.form.get("dark") else "black"),
        "logo": (LOGO_WHITE if request.form.get("dark") else LOGO_BLACK),
        "font_title": FONT_BOLD,
        "font_body":  FONT_REGULAR,
        "font_small": FONT_LIGHT,
        "link": request.form.get("project_link", "").strip()
    }

    file_id = f"poster_{uuid.uuid4().hex}.png"
    out_path = os.path.join(UPLOAD_FOLDER, file_id)
    make_poster(cfg, img_paths, out_path)

    return jsonify({
        "url": f"/poster/{file_id}",
        "filename": f"SDU Project Poster - {cfg['project']}.png"
    })

@app.route("/poster/<path:fname>")
def poster(fname):
    return send_from_directory(UPLOAD_FOLDER, fname, as_attachment=False)

if __name__ == "__main__":
    app.run(debug=True)
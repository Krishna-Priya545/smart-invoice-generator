import os
import re
import sqlite3
import secrets
from io import BytesIO
from datetime import datetime
from xml.sax.saxutils import escape
from email.message import EmailMessage
import smtplib

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, send_file
)
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
)

from pypdf import PdfReader, PdfWriter


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-secret-key")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, "static", "brand-logo.png")

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
SIGNATURE_FOLDER = os.path.join(UPLOAD_FOLDER, "signatures")
SEAL_FOLDER = os.path.join(UPLOAD_FOLDER, "seals")
GENERATED_FOLDER = os.path.join(BASE_DIR, "generated")
DATABASE = os.path.join(BASE_DIR, "invoices.db")

for folder in [
    SIGNATURE_FOLDER,
    SEAL_FOLDER,
    GENERATED_FOLDER
]:
    os.makedirs(folder, exist_ok=True)

GST_OPTIONS = ["GST Inclusive", "GST Exclusive"]
CATEGORY_OPTIONS = ["Product", "Service", "Edutech"]
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg"}
MAX_SIGNATURES = 4


# ---------------- DATABASE ----------------

def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT NOT NULL UNIQUE,
                customer_name TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                billing_date TEXT,
                due_date TEXT,
                purpose TEXT,
                gst_tag TEXT,
                category TEXT,
                total_amount REAL,
                paid_amount REAL,
                balance_amount REAL,
                created_at TEXT NOT NULL,
                file_name TEXT NOT NULL
            )
        """)
        connection.commit()


init_db()


# ---------------- HELPERS ----------------

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def money(value):
    return f"₹ {float(value or 0):,.2f}"


def safe_paragraph(value, style):
    safe_value = escape(str(value or "")).replace("\n", "<br/>")
    return Paragraph(safe_value, style)


def save_signatures(files):
    saved_paths = []

    for file in files:
        if not file or not file.filename:
            continue

        if not allowed_file(file.filename):
            raise ValueError(
                "Signature images must be PNG, JPG or JPEG."
            )

        extension = file.filename.rsplit(".", 1)[1].lower()
        filename = secure_filename(
            f"signature_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_"
            f"{secrets.token_hex(3)}.{extension}"
        )

        path = os.path.join(SIGNATURE_FOLDER, filename)
        file.save(path)
        saved_paths.append(path)

    if len(saved_paths) > MAX_SIGNATURES:
        raise ValueError(
            f"You can upload a maximum of {MAX_SIGNATURES} signatures."
        )

    return saved_paths


def get_latest_signatures(limit=MAX_SIGNATURES):
    files = [
        os.path.join(SIGNATURE_FOLDER, name)
        for name in os.listdir(SIGNATURE_FOLDER)
        if name.lower().endswith((".png", ".jpg", ".jpeg"))
    ]

    files.sort(key=os.path.getmtime, reverse=True)
    return files[:limit]


def save_seal(file):
    if not file or not file.filename:
        return None

    if not allowed_file(file.filename):
        raise ValueError("Seal must be PNG, JPG or JPEG.")

    extension = file.filename.rsplit(".", 1)[1].lower()
    filename = secure_filename(
        f"seal_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.{extension}"
    )

    path = os.path.join(SEAL_FOLDER, filename)
    file.save(path)
    return path


def get_latest_seal():
    files = [
        os.path.join(SEAL_FOLDER, name)
        for name in os.listdir(SEAL_FOLDER)
        if name.lower().endswith((".png", ".jpg", ".jpeg"))
    ]

    if not files:
        return None

    return max(files, key=os.path.getmtime)


def valid_hex(value, fallback):
    value = (value or "").strip()

    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return value

    return fallback


def get_saved_assets(folder):
    return sorted([
        name for name in os.listdir(folder)
        if name.lower().endswith(tuple(ALLOWED_EXTENSIONS))
    ], reverse=True)


# ---------------- PDF GENERATION ----------------

def create_pdf(data, signature_paths=None, seal_path=None):
    signature_paths = signature_paths or []

    bg_hex = valid_hex(data.get("background_color"), "#FFFFFF")
    label_hex = valid_hex(data.get("label_color"), "#183153")
    font_hex = valid_hex(data.get("font_color"), "#26364A")
    accent_hex = valid_hex(data.get("accent_color"), "#0087C9")
    border_hex = valid_hex(data.get("border_color"), "#D7DEE8")

    font_size = max(8, min(14, int(data.get("font_size", 9))))

    font_family = data.get("font_family", "Helvetica")

    font_map = {
        "Arial": "Helvetica",
        "Helvetica": "Helvetica",
        "Times New Roman": "Times-Roman",
        "Courier New": "Courier"
    }

    pdf_font = font_map.get(font_family, "Helvetica")

    pdf_bold = {
        "Helvetica": "Helvetica-Bold",
        "Times-Roman": "Times-Bold",
        "Courier": "Courier-Bold"
    }.get(pdf_font, "Helvetica-Bold")

    bg_color = colors.HexColor(bg_hex)
    label_color = colors.HexColor(label_hex)
    font_color = colors.HexColor(font_hex)
    accent_color = colors.HexColor(accent_hex)
    border_color = colors.HexColor(border_hex)

    layout_style = data.get("layout_style", "Standard")

    page_margin = 12 * mm if layout_style == "Wide" else 18 * mm

    if layout_style == "Compact":
        font_size = max(7, font_size - 1)

    buffer = BytesIO()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=page_margin,
        leftMargin=page_margin,
        topMargin=14 * mm if layout_style == "Compact" else 16 * mm,
        bottomMargin=14 * mm if layout_style == "Compact" else 16 * mm
    )

    styles = getSampleStyleSheet()

    template_name = data.get("template_name", "Modern")

    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=label_color,
        fontName=pdf_bold,
        alignment=0 if (
            layout_style == "Wide"
            or template_name in (
                "Spreadsheet", "Corporate", "Bold",
                "Professional", "Business Pro"
            )
        ) else 1
    )

    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=11,
        textColor=label_color,
        fontName=pdf_bold,
        spaceBefore=12,
        spaceAfter=7
    )

    normal_style = ParagraphStyle(
        "InvoiceNormal",
        parent=styles["Normal"],
        fontSize=font_size,
        leading=font_size + 4,
        textColor=font_color,
        fontName=pdf_font
    )

    small_style = ParagraphStyle(
        "InvoiceSmall",
        parent=styles["Normal"],
        fontSize=max(7, font_size - 1),
        leading=font_size + 2,
        textColor=font_color,
        fontName=pdf_font
    )

    story = []

    # Company seal at the top of the invoice.
    if seal_path and os.path.exists(seal_path):
        top_seal = Image(seal_path, width=30 * mm, height=22 * mm)
        top_seal.hAlign = "RIGHT"
        story.append(top_seal)
        story.append(Spacer(1, 4))

    brand_style = ParagraphStyle(
        "BrandName",
        parent=normal_style,
        fontSize=10,
        leading=13,
        textColor=label_color,
        fontName=pdf_bold
    )

    invoice_meta = ParagraphStyle(
        "InvoiceMeta",
        parent=normal_style,
        fontSize=8.5,
        leading=12,
        alignment=2,
        textColor=font_color,
        fontName=pdf_font
    )

    logo_path = data.get("logo_path") or LOGO_PATH

    logo = (
        Image(logo_path, width=62 * mm, height=17 * mm)
        if os.path.exists(logo_path)
        else Paragraph(
            "INOVATE SOLUTION TECHNOLOGY",
            brand_style
        )
    )

    invoice_title_block = [
        Paragraph("TAX INVOICE", title_style),
        Paragraph(
            f"Invoice No: {escape(data['invoice_number'])}",
            invoice_meta
        ),
        Paragraph(
            f"Generated: {datetime.now().strftime('%d-%m-%Y %I:%M %p')}",
            invoice_meta
        )
    ]

    # ---------------- FIVE TEMPLATE DESIGNS ----------------

    if template_name in ("Classic", "Elegant", "Premium"):

        masthead = Table(
            [[logo], [invoice_title_block]],
            colWidths=[170 * mm]
        )

        masthead.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))

    elif template_name in ("Creative", "Bold", "Executive"):

        masthead = Table(
            [[logo, invoice_title_block]],
            colWidths=[82 * mm, 88 * mm]
        )

        masthead.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), accent_color),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))

    elif template_name in (
        "Spreadsheet", "Continental", "Corporate", "Business Pro"
    ):

        masthead = Table(
            [[logo, invoice_title_block]],
            colWidths=[100 * mm, 70 * mm]
        )

        masthead.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 1.2, accent_color),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))

    else:

        masthead = Table(
            [[logo, invoice_title_block]],
            colWidths=[92 * mm, 78 * mm]
        )

        masthead.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))

    story.append(masthead)

    story.append(
        Table(
            [[""]],
            colWidths=[170 * mm],
            rowHeights=[1.2 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), accent_color)
            ])
        )
    )

    story.append(Spacer(1, 8))

    company_style = ParagraphStyle(
        "CompanyLine",
        parent=normal_style,
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#52657a")
    )

    company_box = Table(
        [[
            Paragraph("Inovate Solution Technology", brand_style),
            Paragraph(
                "Technology · Product · Service · Edutech",
                company_style
            )
        ]],
        colWidths=[85 * mm, 85 * mm]
    )

    company_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg_color),
        ("BOX", (0, 0), (-1, -1), 0.5, border_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    story.append(company_box)

    # ---------------- TEMPLATE TABLE STYLES ----------------

    if template_name == "Spreadsheet":

        data_table_style = [
            ("GRID", (0, 0), (-1, -1), 0.8, accent_color),
            ("BACKGROUND", (0, 0), (0, -1), bg_color)
        ]

    elif template_name in ("Minimal", "Clean", "Compact"):

        data_table_style = [
            ("LINEBELOW", (0, 0), (-1, -1), 0.55, border_color),
            ("BACKGROUND", (0, 0), (0, -1), bg_color)
        ]

    elif template_name in ("Classic", "Elegant", "Premium"):

        data_table_style = [
            ("BOX", (0, 0), (-1, -1), 1, accent_color),
            ("LINEBELOW", (0, 0), (-1, -1), 0.45, border_color),
            ("BACKGROUND", (0, 0), (0, -1), bg_color)
        ]

    elif template_name in ("Creative", "Bold", "Executive"):

        data_table_style = [
            ("BOX", (0, 0), (-1, -1), 0.8, accent_color),
            ("BACKGROUND", (0, 0), (0, -1), accent_color),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.white)
        ]

    elif template_name in (
        "Corporate", "Professional", "Continental", "Business Pro"
    ):

        data_table_style = [
            ("LINEBELOW", (0, 0), (-1, -1), 0.8, accent_color),
            ("BACKGROUND", (0, 0), (0, -1), bg_color),
            ("LINEBEFORE", (1, 0), (1, -1), 1, accent_color)
        ]

    else:

        data_table_style = [
            ("GRID", (0, 0), (-1, -1), 0.5, border_color),
            ("BACKGROUND", (0, 0), (0, -1), bg_color)
        ]

    # ---------------- CUSTOMER INFORMATION ----------------

    story.append(
        Paragraph("CUSTOMER INFORMATION", heading_style)
    )

    customer_rows = [
        ["Customer Name", data["customer_name"]],
        ["Customer Unique ID", data["customer_id"]],
        ["Contact Number", data["contact"]],
        ["Email Address", data["customer_email"]],
        ["Address", data.get("address", "")],
        ["Billing Date", data["billing_date"]]
    ]

    customer_table = Table(
        [
            [
                safe_paragraph(label, normal_style),
                safe_paragraph(value, normal_style)
            ]
            for label, value in customer_rows
        ],
        colWidths=[55 * mm, 115 * mm]
    )

    customer_table.setStyle(
        TableStyle(data_table_style + [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7)
        ])
    )

    story.append(customer_table)

    # ---------------- INVOICE DETAILS ----------------

    story.append(
        Paragraph("INVOICE DETAILS", heading_style)
    )

    invoice_rows = [
        ["Purpose of Invoice", data["purpose"]],
        ["GST Tag", data["gst_tag"]],
        ["Category", data["category"]],
        ["Invoice Template", data.get("template_name", "Modern")]
    ]

    invoice_table = Table(
        [
            [
                safe_paragraph(label, normal_style),
                safe_paragraph(value, normal_style)
            ]
            for label, value in invoice_rows
        ],
        colWidths=[55 * mm, 115 * mm]
    )

    invoice_table.setStyle(
        TableStyle(data_table_style + [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7)
        ])
    )

    story.append(invoice_table)

    # ---------------- BENEFITS ----------------

    benefits = [
        x for x in data["benefits"]
        if x.strip()
    ]

    if benefits:

        story.append(
            Paragraph("BENEFITS", heading_style)
        )

        for index, benefit in enumerate(benefits, 1):
            story.append(
                safe_paragraph(
                    f"{index}. {benefit}",
                    normal_style
                )
            )

    # ---------------- PLANNING SUBSCRIPTIONS ----------------

    subscriptions = [
        x for x in data["subscriptions"]
        if x.strip()
    ]

    if subscriptions:

        story.append(
            Paragraph("PLANNING SUBSCRIPTIONS", heading_style)
        )

        for index, subscription in enumerate(subscriptions, 1):
            story.append(
                safe_paragraph(
                    f"{index}. {subscription}",
                    normal_style
                )
            )

        if data.get("subscription_validity"):
            story.append(
                safe_paragraph(
                    f"Validity: {data['subscription_validity']}",
                    small_style
                )
            )

        if data.get("subscription_next_due"):
            story.append(
                safe_paragraph(
                    f"Next Due Date: {data['subscription_next_due']}",
                    small_style
                )
            )

    # ---------------- PAYMENT INFORMATION ----------------

    story.append(
        Paragraph("PAYMENT INFORMATION", heading_style)
    )

    payment_rows = [
        ["Total Amount", money(data["total_amount"])],
        ["Paid Amount", money(data["paid_amount"])],
        ["Balance Amount", money(data["balance_amount"])],
        [
            "Balance Due Date",
            data.get("balance_due_date") or "Not applicable"
        ]
    ]

    payment_table = Table(
        [
            [
                safe_paragraph(label, normal_style),
                safe_paragraph(value, normal_style)
            ]
            for label, value in payment_rows
        ],
        colWidths=[85 * mm, 85 * mm]
    )

    payment_table.setStyle(
        TableStyle(data_table_style + [
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8)
        ])
    )

    story.append(payment_table)

    # ---------------- REMARKS ----------------

    if data["remarks"]:

        story.append(
            Paragraph("REMARKS", heading_style)
        )

        story.append(
            safe_paragraph(data["remarks"], normal_style)
        )

    # ---------------- MULTIPLE SIGNATURES ----------------

    story.append(Spacer(1, 25))

    story.append(
        Paragraph("SIGNATURES AND SEAL", heading_style)
    )

    signature_cells = []
    signature_labels = []

    for index, path in enumerate(signature_paths, 1):

        if os.path.exists(path):

            img = Image(
                path,
                width=32 * mm,
                height=18 * mm
            )

            img.hAlign = "CENTER"

            signature_cells.append(img)

            signature_labels.append(
                Paragraph(
                    f"Authorized Signature {index}",
                    small_style
                )
            )

    if signature_cells:

        widths = [
            170 * mm / len(signature_cells)
        ] * len(signature_cells)

        signature_table = Table(
            [signature_cells, signature_labels],
            colWidths=widths
        )

        signature_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5)
        ]))

        story.append(signature_table)

    story.append(Spacer(1, 20))

    story.append(
        Paragraph(
            f"Signature Date: {data.get('signature_date') or datetime.now().strftime('%d-%m-%Y')} · Signature Time: {data.get('signature_time') or datetime.now().strftime('%I:%M %p')}",
            small_style
        )
    )

    story.append(
        Paragraph(
            "This is a computer-generated invoice.",
            small_style
        )
    )

    def paint_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(bg_color)
        canvas.rect(
            0, 0,
            A4[0], A4[1],
            fill=1,
            stroke=0
        )
        canvas.restoreState()

    document.build(
        story,
        onFirstPage=paint_page,
        onLaterPages=paint_page
    )

    buffer.seek(0)

    return buffer


# ---------------- PDF ENCRYPTION ----------------

def password_protect_pdf(pdf_buffer, phone_password):

    reader = PdfReader(pdf_buffer)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    writer.encrypt(
        user_password=phone_password,
        owner_password=secrets.token_urlsafe(24),
        algorithm="AES-256"
    )

    protected_buffer = BytesIO()

    writer.write(protected_buffer)

    protected_buffer.seek(0)

    return protected_buffer


# ---------------- EMAIL ----------------

def send_invoice_email(
    recipient,
    filename,
    pdf_bytes,
    customer_name
):

    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")

    if not all([
        smtp_server,
        smtp_user,
        smtp_password
    ]):
        raise ValueError(
            "Please configure your email settings in .env."
        )

    message = EmailMessage()

    message["Subject"] = "Your Invoice"
    message["From"] = smtp_user
    message["To"] = recipient

    message.set_content(
        f"""Hello {customer_name},

Your invoice is attached.

The PDF is password protected. Use your registered phone number
(digits only, including country code if entered) to open it.

Regards,
Invoice Team
"""
    )

    message.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=filename
    )

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(message)


# ---------------- INVOICE HISTORY ----------------

def search_invoices(search_text=""):

    with get_db() as connection:

        if search_text:

            rows = connection.execute("""
                SELECT * FROM invoices
                WHERE customer_name LIKE ?
                ORDER BY id DESC
            """, (f"%{search_text}%",)).fetchall()

        else:

            rows = connection.execute("""
                SELECT * FROM invoices
                ORDER BY id DESC
            """).fetchall()

    return rows


# ---------------- HOME PAGE ----------------

@app.route("/")
def index():

    search_text = request.args.get(
        "search", ""
    ).strip()

    invoices = search_invoices(search_text)

    return render_template(
        "index.html",
        invoices=invoices,
        search_text=search_text,
        gst_options=GST_OPTIONS,
        category_options=CATEGORY_OPTIONS,
        saved_signatures=get_saved_assets(SIGNATURE_FOLDER),
        saved_seals=get_saved_assets(SEAL_FOLDER)
    )


# ---------------- DOWNLOAD INVOICE ----------------

@app.route("/download/<int:invoice_id>")
def download_invoice(invoice_id):

    with get_db() as connection:

        invoice = connection.execute(
            "SELECT * FROM invoices WHERE id = ?",
            (invoice_id,)
        ).fetchone()

    if not invoice:

        flash("Invoice not found.", "error")

        return redirect(url_for("index"))

    file_path = os.path.join(
        GENERATED_FOLDER,
        invoice["file_name"]
    )

    if not os.path.isfile(file_path):

        flash(
            "Invoice PDF file could not be found.",
            "error"
        )

        return redirect(url_for("index"))

    return send_file(
        file_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=invoice["file_name"]
    )


# ---------------- SIGNATURE ASSET ----------------

@app.route("/assets/signatures/<path:filename>")
def signature_asset(filename):

    return send_file(
        os.path.join(
            SIGNATURE_FOLDER,
            secure_filename(filename)
        )
    )


# ---------------- GENERATE INVOICE ----------------

@app.route("/generate", methods=["POST"])
def generate_invoice():

    try:

        customer_name = request.form.get(
            "customer_name", ""
        ).strip()

        customer_id = request.form.get(
            "customer_id", ""
        ).strip()

        contact = request.form.get(
            "contact", ""
        ).strip()

        customer_email = request.form.get(
            "customer_email", ""
        ).strip()

        address = request.form.get(
            "address", ""
        ).strip()

        billing_date = request.form.get(
            "billing_date", ""
        ).strip()

        balance_due_date = request.form.get(
            "balance_due_date", ""
        ).strip()

        purpose = request.form.get(
            "purpose", ""
        ).strip()

        gst_tag = request.form.get(
            "gst_tag", ""
        ).strip()

        category = request.form.get(
            "category", ""
        ).strip()

        benefits = [
            request.form.get("benefit1", "").strip(),
            request.form.get("benefit2", "").strip()
        ]

        subscriptions = [
            request.form.get("subscription1", "").strip(),
            request.form.get("subscription2", "").strip()
        ]

        total_amount = float(
            request.form.get("total_amount", "0")
        )

        paid_amount = float(
            request.form.get("paid_amount", "0")
        )

        # ---------------- VALIDATION ----------------

        if not customer_name or not customer_id or not customer_email:

            raise ValueError(
                "Customer name, unique ID and email are required."
            )

        if not contact:

            raise ValueError(
                "Customer phone number is required."
            )

        # Phone number digits become the PDF password.
        phone_password = re.sub(
            r"\D", "", contact
        )

        if not 8 <= len(phone_password) <= 15:

            raise ValueError(
                "Enter a valid customer phone number with 8 to 15 digits."
            )

        if not purpose:

            raise ValueError(
                "Please enter the purpose of the invoice."
            )

        if gst_tag not in GST_OPTIONS:

            raise ValueError(
                "Please select a valid GST Tag."
            )

        if category not in CATEGORY_OPTIONS:

            raise ValueError(
                "Please select a valid category."
            )

        if total_amount < 0 or paid_amount < 0:

            raise ValueError(
                "Amounts cannot be negative."
            )

        if paid_amount > total_amount:

            raise ValueError(
                "Paid amount cannot exceed total amount."
            )

        balance_amount = total_amount - paid_amount

        if balance_amount > 0:

            if not balance_due_date:

                raise ValueError(
                    "Please enter the balance due date when an amount is outstanding."
                )

            if billing_date and balance_due_date < billing_date:

                raise ValueError(
                    "Balance due date cannot be earlier than billing date."
                )

        # ---------------- SIGNATURES ----------------

        signature_files = request.files.getlist(
            "signatures"
        )

        signature_paths = save_signatures(
            signature_files
        )

        if (
            not signature_paths
            and request.form.get("reuse_signatures") == "yes"
        ):

            signature_paths = get_latest_signatures()

        selected_signatures = request.form.getlist(
            "selected_signatures"
        )

        if selected_signatures:

            signature_paths = [
                os.path.join(
                    SIGNATURE_FOLDER,
                    secure_filename(name)
                )
                for name in selected_signatures
                if os.path.isfile(
                    os.path.join(
                        SIGNATURE_FOLDER,
                        secure_filename(name)
                    )
                )
            ]

        if len(signature_paths) > MAX_SIGNATURES:

            raise ValueError(
                f"Maximum {MAX_SIGNATURES} signatures are allowed."
            )

        # ---------------- COMPANY SEAL ----------------

        seal_path = save_seal(
            request.files.get("seal")
        )

        if (
            not seal_path
            and request.form.get("reuse_seal") == "yes"
        ):

            seal_path = get_latest_seal()

        selected_seal = secure_filename(
            request.form.get("selected_seal", "")
        )

        if (
            selected_seal
            and os.path.isfile(
                os.path.join(SEAL_FOLDER, selected_seal)
            )
        ):

            seal_path = os.path.join(
                SEAL_FOLDER,
                selected_seal
            )

        # ---------------- INVOICE NUMBER ----------------

        invoice_number = (
            f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}-"
            f"{secrets.token_hex(2).upper()}"
        )

        # ---------------- INVOICE DATA ----------------

        data = {
            "invoice_number": invoice_number,
            "customer_name": customer_name,
            "customer_id": customer_id,
            "contact": contact,
            "customer_email": customer_email,
            "address": address,
            "billing_date": billing_date,
            "balance_due_date": balance_due_date,
            "purpose": purpose,
            "gst_tag": gst_tag,
            "category": category,
            "benefits": benefits,
            "subscriptions": subscriptions,
            "total_amount": total_amount,
            "paid_amount": paid_amount,
            "balance_amount": balance_amount,
            "remarks": request.form.get(
                "remarks", ""
            ).strip(),

            "subscription_validity": request.form.get(
                "subscription_validity", ""
            ).strip(),

            "subscription_next_due": request.form.get(
                "subscription_next_due", ""
            ).strip(),

            "signature_date": request.form.get(
                "signature_date", ""
            ).strip(),

            "signature_time": request.form.get(
                "signature_time", ""
            ).strip(),

            "template_name": request.form.get(
                "template_name", "Modern"
            ),

            "background_color": valid_hex(
                request.form.get("background_color"),
                "#FFFFFF"
            ),

            "label_color": valid_hex(
                request.form.get("label_color"),
                "#183153"
            ),

            "font_color": valid_hex(
                request.form.get("font_color"),
                "#26364A"
            ),

            "accent_color": valid_hex(
                request.form.get("accent_color"),
                "#0087C9"
            ),

            "border_color": valid_hex(
                request.form.get("border_color"),
                "#D7DEE8"
            ),

            "font_family": request.form.get(
                "font_family", "Helvetica"
            ),

            "font_size": request.form.get(
                "font_size", "9"
            ),

            "layout_style": request.form.get(
                "layout_style", "Standard"
            )
        }

        # ---------------- CREATE PDF ----------------

        pdf_buffer = create_pdf(
            data,
            signature_paths,
            seal_path
        )

        # ---------------- PASSWORD PROTECTION ----------------

        protected_pdf = password_protect_pdf(
            pdf_buffer,
            phone_password
        )

        filename = f"{invoice_number}.pdf"

        file_path = os.path.join(
            GENERATED_FOLDER,
            filename
        )

        with open(file_path, "wb") as output:

            output.write(
                protected_pdf.getvalue()
            )

        # ---------------- SAVE TO DATABASE ----------------

        with get_db() as connection:

            connection.execute("""
                INSERT INTO invoices (
                    invoice_number,
                    customer_name,
                    customer_phone,
                    customer_email,
                    billing_date,
                    due_date,
                    purpose,
                    gst_tag,
                    category,
                    total_amount,
                    paid_amount,
                    balance_amount,
                    created_at,
                    file_name
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                invoice_number,
                customer_name,
                contact,
                customer_email,
                billing_date,
                "",
                purpose,
                gst_tag,
                category,
                total_amount,
                paid_amount,
                balance_amount,
                datetime.now().strftime(
                    "%d-%m-%Y %I:%M %p"
                ),
                filename
            ))

            connection.commit()

        # ---------------- OPTIONAL EMAIL ----------------

        if request.form.get("send_email") == "yes":

            try:

                send_invoice_email(
                    customer_email,
                    filename,
                    protected_pdf.getvalue(),
                    customer_name
                )

                flash(
                    "Invoice created and emailed successfully.",
                    "success"
                )

            except Exception as email_error:

                app.logger.exception(
                    "Invoice email failed"
                )

                flash(
                    f"Invoice saved, but email could not be sent: {email_error}",
                    "error"
                )

        else:

            flash(
                "Invoice created successfully.",
                "success"
            )

        return redirect(
            url_for("index")
        )

    except ValueError as error:

        flash(
            str(error),
            "error"
        )

        return redirect(
            url_for("index")
        )

    except Exception as error:

        app.logger.exception(
            "Invoice generation failed"
        )

        flash(
            f"Could not generate invoice: {error}",
            "error"
        )

        return redirect(
            url_for("index")
        )


# ---------------- RUN APPLICATION ----------------

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5002,
        debug=True
    )
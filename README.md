# Smart Invoice Generator — Flask

A Flask invoice generator with encrypted PDF output, invoice history, optional Gmail SMTP delivery, saved signature/seal assets, and a customizable invoice designer.

## New design features
- 15 templates: Standard, Spreadsheet, Continental, Compact, Classic, Modern, Minimal, Corporate, Elegant, Creative, Executive, Premium, Professional, Bold and Clean.
- Background, label, font, accent and table-border color controls.
- Helvetica, Arial, Times New Roman and Courier New font choices; adjustable PDF font size.
- Standard, Wide, Compact and Centered layout options.
- Live preview updates while editing.
- Save/load custom designs in the current browser using local storage.
- Upload and reuse company seals and multiple authorized signatures.
- Design choices are applied to the PDF as well as the browser preview.

## Requirements
- Python 3.10+
- macOS, Windows or Linux

## Setup on macOS
```bash
cd "invoice gen"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```
Open http://127.0.0.1:5002

If port 5002 is occupied, stop the other process or change the port at the bottom of `app.py`.

## Important existing data
Before replacing an existing project, copy these items from your old folder into the new one:
- `invoices.db` (invoice history)
- `uploads/signatures/`
- `uploads/seals/`
- `.env` (SMTP settings and secret key)
- `generated/` (previous PDF files)

Do not share `.env` or the generated encrypted PDFs publicly. The PDF password is based on the customer's phone number as configured in this project.

## Email configuration
Edit `.env` and set `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `FLASK_SECRET_KEY`. For Gmail, use a Google App Password, not your normal Google password.

## Saved designs
Custom designs are saved in browser local storage on the same browser/device. They are not stored in SQLite and will not automatically move to another computer/browser.

## Latest interface updates
- Removed the customer due-date field; billing date remains.
- Removed the invoice-logo upload control. The built-in company branding remains in the PDF header.
- Moved company-seal upload to the top of the form and placed the seal at the top of generated invoices.
- Removed custom fields from the form and generated PDF.
- The 15 invoice templates now use different header arrangements and table treatments in the PDF, as well as distinct color palettes.
- The balance due date remains under Payment Information and is required only when an amount is outstanding.

The existing SQLite database is retained. Its legacy `due_date` column remains for compatibility and is saved as blank for newly generated invoices.

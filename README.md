<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Flask-3.0+-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask">
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License">
</p>

<h1 align="center">📧 Bulk Certificate Emailer</h1>

<p align="center">
  Generate personalized PDF certificates from Word templates and email them to hundreds of recipients — all from one beautiful web interface.
</p>

<p align="center">
  <a href="#-features">Features</a> •
  <a href="#-screenshots">Screenshots</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-how-it-works">How It Works</a> •
  <a href="#%EF%B8%8F-configuration">Configuration</a> •
  <a href="#-project-structure">Project Structure</a> •
  <a href="#-troubleshooting">Troubleshooting</a>
</p>

---

## ✨ Features

- **Smart Data Import** — Upload CSV or Excel files with automatic format correction, encoding detection, and column mapping
- **Template Engine** — Use branded `.docx` Word templates with `{{placeholders}}` that get replaced per recipient
- **Rich Email Editor** — Compose HTML emails with formatting, images, and signatures via a full WYSIWYG editor
- **Bulk Processing** — Generate PDFs and send emails with real-time progress tracking and automatic retry on failures
- **Modern Web UI** — Dark/light theme, responsive design, step-by-step wizard with sidebar navigation
- **One-Command Setup** — Automated `setup.py` script creates a virtual environment, installs dependencies, and launches the app

---

## 📸 Screenshots

| Home Page | Data & Mapping |
|:-:|:-:|
| ![Home](./screenshots/1.png) | ![Data](./screenshots/2.png) |

| Template Preview | Email Configuration |
|:-:|:-:|
| ![Template](./screenshots/3.png) | ![Email](./screenshots/4.png) |

| Processing |
|:-:|
| ![Run](./screenshots/5.png) |

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **LibreOffice** (for `.docx` → PDF conversion) — [Download](https://www.libreoffice.org/download/download/)
- **Gmail account** with an [App Password](https://myaccount.google.com/apppasswords) enabled

### Setup (One Command)

```bash
cd web_app
python setup.py
```

This will:
1. Create a Python virtual environment (`.venv`)
2. Install all dependencies from `requirements.txt`
3. Verify LibreOffice is installed
4. Launch the web app at **http://127.0.0.1:5050**

### Manual Setup

```bash
cd web_app
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5050** in your browser.

---

## 🔄 How It Works

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  1. Upload   │───▶│  2. Template │───▶│ 3. Configure │───▶│   4. Send    │
│  CSV/Excel   │    │  .docx file  │    │  Gmail Auth  │    │  Bulk Email  │
│  with data   │    │  with {{}}   │    │  + Email body│    │  with PDFs   │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
```

1. **Upload Data** — Import your Excel or CSV with names, emails, and other fields. The app auto-detects encoding, fixes formatting issues, and lets you map columns to placeholders.

2. **Add Template** — Upload a `.docx` certificate template containing `{{placeholders}}` (e.g., `{{name}}`, `{{event}}`). These get replaced with each recipient's data.

3. **Configure** — Enter your Gmail credentials (using an App Password), compose the email subject and body with the rich text editor, and set the PDF filename pattern.

4. **Send** — Hit start and watch certificates get generated and emailed in real time. Failed emails are automatically retried, and a failure log is available for download.

---

## ⚙️ Configuration

### Gmail App Password

1. Go to [Google Account → App Passwords](https://myaccount.google.com/apppasswords)
2. Select **Mail** and your device
3. Copy the 16-character password
4. Paste it in the **Authentication** step of the app

> **Note:** You must have 2-Step Verification enabled on your Google account to generate App Passwords.

### Template Placeholders

Your `.docx` template should contain Jinja2-style placeholders:

```
Dear {{name}},

This certificate is awarded to {{name}} for participating in {{event}}
held on {{date}}.

Congratulations!
```

The placeholder names must match the column mappings you configure in Step 1.

### Email Body Placeholders

The email body also supports `{{placeholder}}` syntax for personalization:

```
Dear {{name}},

Please find attached your certificate for {{event}}.

Best regards,
The Organizing Team
```

---

## 📁 Project Structure

```
web_app/
├── app.py                 # Flask server & API routes
├── setup.py               # One-command setup & bootstrap
├── config.py              # Path management & config I/O
├── config.json            # Saved credentials & settings
├── requirements.txt       # Python dependencies
├── README.md              # This file
├── .gitignore             # Git ignore rules
├── services/
│   ├── data_service.py    # CSV/Excel parsing & auto-correction
│   ├── template_service.py# .docx template processing & PDF generation
│   ├── email_service.py   # Gmail SMTP sending with retry
│   └── task_service.py    # Background task orchestration & SSE progress
├── templates/
│   └── index.html         # Single-page application
├── static/
│   ├── css/style.css      # Production styles (dark/light theme)
│   └── js/app.js          # Frontend logic & state management
├── uploads/               # Temporary uploaded files
└── certificates/          # Generated PDF certificates
```

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `flask` | Web framework & API server |
| `pandas` | Data manipulation & CSV/Excel parsing |
| `openpyxl` | Excel file reading |
| `docxtpl` | Word template rendering with Jinja2 |
| `docx2pdf` | PDF conversion via LibreOffice |
| `mammoth` | .docx → HTML preview conversion |
| `retrying` | Automatic retry for failed email sends |

---

## 🔧 Troubleshooting

### "LibreOffice not found"
Install LibreOffice from [libreoffice.org](https://www.libreoffice.org/download/download/). On macOS:
```bash
brew install --cask libreoffice
```

### "SMTP Authentication Error"
- Ensure you're using an **App Password**, not your regular Gmail password
- Verify 2-Step Verification is enabled on your Google account
- Check that "Less secure app access" is not blocking the connection

### "ModuleNotFoundError"
Run the setup script to install all dependencies:
```bash
cd web_app
python setup.py
```

### Port Already in Use
The app runs on port **5050** by default. If it's occupied, edit the last line in `app.py`:
```python
app.run(debug=True, port=YOUR_PORT, threaded=True)
```

---

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

---

<p align="center">
  Made with ❤️ by <strong>Ekansh Chauhan</strong>
</p>

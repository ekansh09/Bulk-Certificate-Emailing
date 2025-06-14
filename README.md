# Bulk Attachment Personalizer & Emailer

A cross-platform PyQt5 application to generate and send personalized PDF (or other) attachments in bulk from a Word template and spreadsheet data via Gmail.

**Author:** Ekansh Chauhan
**Email:** [echauhan09@gmail.com](mailto:echauhan09@gmail.com)

## 🌟 Use Cases

Whether you’re organizing events or sending personalized attachments at scale, this app lets you:

* 🎟️ Automate certificate issuance for events, workshops, and training sessions.
* ✉️ Send personalized event invitations, thank-you letters, or newsletters at scale.
* 📄 Generate individualized billing statements, invoices, or financial summaries.
* 🆔 Dispatch customized membership cards, badges, or access passes.
* 🎓 Produce tailored onboarding documents for new employees, students, or volunteers.
* 📣 Deliver personalized marketing flyers, promotions, or coupons.
* 💌 Issue customized donation receipts or fundraising acknowledgments.
* 📊 Create individualized progress reports, performance reviews, or educational transcripts.

Leverage a single template and spreadsheet to streamline any bulk-document workflow—boost productivity, reduce errors, and enhance personalization.

---

## 📸 Screenshots

Below are screenshots showcasing each main page (tab) and its functionality:

| Data Mapping                    | Template Preview                    | Authentication                    |
| ------------------------------- | ----------------------------------- | --------------------------------- |
| ![Data Mapping](./screenshots/1.png) | ![Template Preview](./screenshots/2.png) | ![Authentication](./screenshots/3.png) |

| Email & Filename                    | Run & Progress                    |
| ----------------------------------- | --------------------------------- |
| ![Email & Filename](./screenshots/4.png) | ![Run & Progress](./screenshots/5.png) |

## 🚀 Features

1. **Data Import & Mapping**

   * Load Excel (`.xlsx`) or CSV (`.csv`) contact and content lists.
   * Map sheet columns to lowercase Jinja-style placeholders (e.g. `name`, `id`, `email`, `role`).
   * Auto-detect the `email` column for bulk emailing recipients.

2. **Template Preview**

   * Load a `.docx` template containing `{{placeholders}}`.
   * Live HTML preview with zoom controls before bulk generation.

3. **Authentication**

   * Enter Gmail address and App Password in the **Authentication** tab.
   * Securely save credentials in `config.json`.
   * Test SMTP connection to verify bulk emailing capability.

4. **Attachment & Email Configuration**

   * Specify email subject, body, and filename pattern using any mapped placeholders.
   * Default patterns provided; all fields mandatory for personalized emailing.
   * Real-time list of available placeholders for easy copy-&-paste.

5. **Preview & Confirm**

   * Optionally generate and open the first attachment (e.g., certificate, letter, report) PDF to verify content and layout before sending in bulk.

6. **Batch Generation & Delivery**

   * Renders each row into a `.docx`, converts to PDF (or retains chosen format), then sends via Gmail SMTP with retry logic.
   * Progress bar shows percent complete and count (e.g. “23/100”).
   * Detailed log of successes and failures; export `failed_list.csv`.

7. **Error Handling**

   * Detects unmapped or improperly cased placeholders in the template and email content.
   * Prevents sending until all tags match.
   * Catches network or SMTP errors with automatic retries.

8. **Packaging**

   * Package into a standalone executable via PyInstaller for easy distribution.

---

---

## 🛠️ Installation

> ⚠️ **Windows users:** For proper permissions, run `app.py` or `run_app.bat` as **Administrator**.

1. **Clone the repository**

   ```bash
   git clone https://github.com/ekansh09/Bulk-Certificate-Emailing.git
   cd Bulk-Certificate-Emailing
   ```

2. **Create a virtual environment & install dependencies**

   ```bash
   python3 -m venv venv
   # Activate the venv
   # macOS/Linux:
   source venv/bin/activate
   # Windows (PowerShell):
   # venv\Scripts\Activate
   pip install -r requirements.txt
   ```

3. **Run the app**

   * **Directly with Python**

     ```bash
     python app.py
     ```

   * **Windows (Optional Batch Script)**

     1. Open `run_app.bat` in a text editor.
     2. Update the `TARGET_DIR` variable to the full path of your cloned project, e.g.:

        ```bat
        set "TARGET_DIR=C:\Projects\Bulk-Certificate-Emailing"
        ```
     3. Save the file.
     4. Right-click `run_app.bat` and select **Run as administrator** to launch the app.

4. **(Optional) Package the app**

   ```bash
   pip install pyinstaller
   pyinstaller --noconsole --onefile app.py
   ```

---

## ⚙️ Configuration

1. **Gmail App Password**

   * Generate a 16-character App Password via your Google Account settings.
   * Enter it on the **Authentication** tab with your Gmail address, then click **Test Connection** and **Save Credentials**.

2. **Spreadsheet**

   * Ensure your sheet has an `email` column plus any other data columns you wish to merge into attachments.
   * Example: `id, name, report_data, email` or `s_no, name, status, email`.

3. **Word Template**

   * Use lowercase Jinja-style tags matching your placeholders, for example:

     ```text
     Report for {{name}}
     Status: {{status}}
     Details: {{report_data}}
     ```

---

## 🚀 Usage

1. **Load Data & Map Columns**

   * In **Data & Mapping** tab: click **Load Excel/CSV**, map columns to placeholders.

2. **Load Template & Preview**

   * Switch to **Template Preview**, click **Load .docx Template**, zoom/scroll to inspect.

3. **Authenticate**

   * Go to **Authentication** tab, enter Gmail & App Password, click **Test Connection**, then **Save Credentials**.

4. **Configure Attachment & Email**

   * In **Email & Filename** tab: select `email` column, edit subject/body, set filename pattern (e.g. `Attachment_{{name}}.pdf`).

5. **Preview First Attachment** (optional)

   * Check **Preview first PDF** to generate/open the first personalized attachment before bulk sending.

6. **Start Bulk Generation & Email**

   * Go to **Run & Progress**, click **Start Processing**.
   * Monitor the progress bar and counter (e.g. “12/100”).
   * Review live log; export `failed_list.csv` if any deliveries failed.

---

## 💡 Troubleshooting

* **Access Errors**: Try running with administrator access.
* **Tag Errors**: Alerts for undefined or uppercase placeholders.
* **Slow Performance**: Disable preview or reduce batch size.
* **Packaging Issues**: See [PyInstaller docs](https://pyinstaller.org).

---

## 📄 License

This project is licensed under the MIT License.
© Ekansh Chauhan

"""
Conference Certificate Generator Application

Author: Ekansh Chauhan
Date: June 7, 2025
Description: PyQt5-based certificate generation and emailing application.
"""

import sys
import os
import tempfile
import re
import json
import pandas as pd
import mammoth
from docxtpl import DocxTemplate
from docx2pdf import convert
import smtplib
from retrying import retry
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QPushButton, QLabel,
    QLineEdit, QProgressBar, QTextEdit, QFileDialog, QTableWidget,
    QTableWidgetItem, QListWidget, QVBoxLayout, QHBoxLayout, QComboBox,
    QMessageBox, QGroupBox, QFormLayout
)
from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QThread
from PyQt5.QtWebEngineWidgets import QWebEngineView

# Determine application directory (handles PyInstaller)
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(APP_DIR, 'config.json')
CERT_DIR = os.path.join(APP_DIR, 'certificates')


class Worker(QObject):
    """
    Handles generation of certificates and email dispatch.

    Author: Ekansh Chauhan
    """
    progress_updated = pyqtSignal(int)
    count_updated = pyqtSignal(int, int)
    log_message = pyqtSignal(str)
    finished = pyqtSignal(int, list)

    def __init__(self, data_df, template_path, mapping, recipient_col,
                 email_subj, email_body, filename_pattern, auth_user, auth_pwd):
        super().__init__()
        self.data_df = data_df
        self.template_path = template_path
        self.mapping = mapping
        self.recipient_col = recipient_col
        self.email_subj = email_subj.replace('{{', '{').replace('}}', '}')
        self.email_body = email_body.replace('{{', '{').replace('}}', '}')
        self.filename_pattern = filename_pattern.replace('{{', '{').replace('}}', '}')
        self.auth_user = auth_user
        self.auth_pwd = auth_pwd

    def run(self):
        total = len(self.data_df)
        sent, failed = 0, []
        for i, row in self.data_df.iterrows():
            context = {ph: str(row[col]) for ph, col in self.mapping.items()}
            recipient = str(row[self.recipient_col])
            try:
                pdf_path = self.generate_certificate(context)
                self.send_email(recipient, context, pdf_path)
                sent += 1
                self.log_message.emit(f"Sent to {recipient}")
            except Exception as e:
                failed.append((recipient, str(e)))
                self.log_message.emit(f"Failed for {recipient}: {e}")

            # Update after each attempt
            processed = sent + len(failed)
            percent = int((processed / total) * 100)
            self.count_updated.emit(processed, total)
            self.progress_updated.emit(percent)

        # Finalize
        self.count_updated.emit(total, total)
        self.progress_updated.emit(100)
        self.finished.emit(sent, failed)

    def generate_certificate(self, context):
        tpl = DocxTemplate(self.template_path)
        tpl.render(context)
        tmp_docx = tempfile.NamedTemporaryFile(suffix='.docx', delete=False).name
        tpl.save(tmp_docx)
        filename = self.filename_pattern.format(**context)
        if not filename.lower().endswith('.pdf'):
            filename += '.pdf'
        # Ensure certificates directory exists
        os.makedirs(CERT_DIR, exist_ok=True)
        out_path = os.path.join(CERT_DIR, filename)
        convert(tmp_docx, out_path)
        return out_path

    @retry(stop_max_attempt_number=3, wait_fixed=2000)
    def send_email(self, recipient, context, attachment_path):
        if not self.auth_user or not self.auth_pwd:
            raise ValueError("Gmail credentials not set.")
        msg = MIMEMultipart()
        msg['Subject'] = self.email_subj.format(**context)
        msg['From'] = self.auth_user
        msg['To'] = recipient
        msg.attach(MIMEText(self.email_body.format(**context), 'plain'))
        with open(attachment_path, 'rb') as f:
            part = MIMEApplication(f.read(), _subtype='pdf')
        part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(attachment_path))
        msg.attach(part)
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(self.auth_user, self.auth_pwd)
            server.send_message(msg)

class CertGenerator(QMainWindow):
    """
    Conference Certificate Generator GUI.

    Author: Ekansh Chauhan
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Conference Certificate Generator")
        self.resize(1000, 800)
        self.data_df = None
        self.template_path = None
        self.auth_user = ''
        self.auth_pwd = ''
        self.thread = None
        self.worker = None
        self.load_config()
        self.setup_ui()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                cfg = json.load(open(CONFIG_FILE))
                self.auth_user = cfg.get('email', '')
                self.auth_pwd = cfg.get('app_password', '')
            except:
                pass

    def save_config(self):
        cfg = {'email': self.auth_user, 'app_password': self.auth_pwd}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f)

    def setup_ui(self):
        self.tabs = QTabWidget()
        self.tab_data = QWidget(); self.setup_tab_data()
        self.tab_preview = QWidget(); self.setup_tab_preview()
        self.tab_auth = QWidget(); self.setup_tab_auth()
        self.tab_email = QWidget(); self.setup_tab_email()
        self.tab_run = QWidget(); self.setup_tab_run()
        for w, title in [
            (self.tab_data, "Data & Mapping"),
            (self.tab_preview, "Template Preview"),
            (self.tab_auth, "Authentication"),
            (self.tab_email, "Email & Filename"),
            (self.tab_run, "Run & Progress")]:
            self.tabs.addTab(w, title)
        self.setCentralWidget(self.tabs)

    def setup_tab_data(self):
        layout = QVBoxLayout()
        # Load button
        btn_load = QPushButton("Load Excel/CSV")
        btn_load.clicked.connect(self.load_data)
        layout.addWidget(btn_load)
        # Column-to-placeholder mapping table
        self.map_table = QTableWidget(0, 2)
        self.map_table.setHorizontalHeaderLabels(['Column', 'Placeholder'])
        layout.addWidget(QLabel("Map each column to a Jinja placeholder (lowercase, alphanumeric/_):"))
        layout.addWidget(self.map_table)
        # Data preview table (max 5 rows)
        layout.addWidget(QLabel("Data Preview (5 rows):"))
        self.data_preview = QTableWidget()
        self.data_preview.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.data_preview)
        # Navigation for preview
        nav_layout = QHBoxLayout()
        self.btn_prev = QPushButton("Prev")
        self.btn_prev.clicked.connect(self.prev_page)
        self.btn_next = QPushButton("Next")
        self.btn_next.clicked.connect(self.next_page)
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addStretch()
        layout.addLayout(nav_layout)
        self.tab_data.setLayout(layout)

    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_data_preview()

    def next_page(self):
        max_page = (len(self.data_df) - 1) // self.rows_per_page
        if self.current_page < max_page:
            self.current_page += 1
            self.update_data_preview()

    def update_data_preview(self):
        # Show up to rows_per_page rows starting at current_page*rows_per_page
        start = self.current_page * self.rows_per_page
        end = min(start + self.rows_per_page, len(self.data_df))
        chunk = self.data_df.iloc[start:end]
        # Include index column
        cols = ["_index_"] + list(self.data_df.columns)
        self.data_preview.clear()
        self.data_preview.setColumnCount(len(cols))
        self.data_preview.setHorizontalHeaderLabels(cols)
        self.data_preview.setRowCount(len(chunk))
        for i, (idx, row) in enumerate(chunk.iterrows()):
            # Index cell
            self.data_preview.setItem(i, 0, QTableWidgetItem(str(idx)))
            for j, col in enumerate(self.data_df.columns, start=1):
                self.data_preview.setItem(i, j, QTableWidgetItem(str(row[col])))
        # Update nav buttons
        self.btn_prev.setEnabled(self.current_page > 0)
        max_page = (len(self.data_df) - 1) // self.rows_per_page
        self.btn_next.setEnabled(self.current_page < max_page)
        self.btn_prev.setEnabled(self.current_page > 0)
        max_page = (len(self.data_df) - 1) // self.rows_per_page
        self.btn_next.setEnabled(self.current_page < max_page)

    def setup_tab_preview(self):
        layout = QVBoxLayout()
        btn_temp = QPushButton("Load .docx Template")
        btn_temp.clicked.connect(self.load_template)
        layout.addWidget(btn_temp)
        zoom_layout = QHBoxLayout()
        zi = QPushButton("Zoom In"); zo = QPushButton("Zoom Out")
        zi.clicked.connect(lambda: self.set_zoom(1.2))
        zo.clicked.connect(lambda: self.set_zoom(0.8))
        zoom_layout.addWidget(zi); zoom_layout.addWidget(zo); zoom_layout.addStretch()
        layout.addLayout(zoom_layout)
        self.preview = QWebEngineView()
        layout.addWidget(self.preview)
        self.tab_preview.setLayout(layout)

    def setup_tab_email(self):
        layout = QVBoxLayout()
        # Recipient Email Column
        layout.addWidget(QLabel("Recipient Email Column:"))
        self.cb_recipient = QComboBox()
        layout.addWidget(self.cb_recipient)
        # Email Subject
        layout.addWidget(QLabel("Email Subject (use {{placeholders}}):"))
        self.email_subj = QLineEdit("CERTIFICATE")
        layout.addWidget(self.email_subj)
                # Email Body
        layout.addWidget(QLabel("Email Body (use {{placeholders}}):"))
        self.email_body = QTextEdit("Thank you for your support to make it a successful conference, Best Regards, Conf Org.")
        layout.addWidget(self.email_body)
        # Filename Pattern
        layout.addWidget(QLabel("Filename Pattern (e.g. certificate_{{name}}.pdf):"))
        self.filename_pattern = QLineEdit("certificate_{{name}}.pdf")
        layout.addWidget(self.filename_pattern)
        # Available Placeholders
        layout.addWidget(QLabel("Available Placeholders:"))
        self.vars_list = QListWidget()
        layout.addWidget(self.vars_list)
        # Preview Option
        self.chk_preview = QPushButton("Preview first PDF")
        self.chk_preview.setCheckable(True)
        layout.addWidget(self.chk_preview)
        # Dark Mode
        self.chk_dark = QPushButton("Dark Mode")
        self.chk_dark.setCheckable(True)
        self.chk_dark.clicked.connect(self.toggle_theme)
        layout.addWidget(self.chk_dark)
        self.tab_email.setLayout(layout)

    def setup_tab_run(self):
        layout = QVBoxLayout()
        btn_start = QPushButton("Start Processing")
        btn_start.clicked.connect(self.start_process)
        layout.addWidget(btn_start)
        # Progress bar and count label
        bar_layout = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        bar_layout.addWidget(self.progress)
        self.progress_label = QLabel("0/0")
        bar_layout.addWidget(self.progress_label)
        layout.addLayout(bar_layout)
        # Log
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        self.tab_run.setLayout(layout)

    def setup_tab_auth(self):
        layout = QVBoxLayout()
        # Gmail Authentication Group
        auth_group = QGroupBox("Gmail Authentication")
        form = QFormLayout()
        # Email address
        self.auth_email_input = QLineEdit(self.auth_user)
        self.auth_email_input.setMinimumWidth(300)
        self.auth_email_input.setPlaceholderText("you@example.com")
        form.addRow(QLabel("Email Address:"), self.auth_email_input)
        # App password
        self.auth_pwd_input = QLineEdit(self.auth_pwd)
        self.auth_pwd_input.setMinimumWidth(300)
        self.auth_pwd_input.setEchoMode(QLineEdit.Password)
        self.auth_pwd_input.setPlaceholderText("App Password (16 chars)")
        form.addRow(QLabel("App Password:"), self.auth_pwd_input)
        auth_group.setLayout(form)
        layout.addWidget(auth_group)
        # Buttons
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("Save Credentials")
        btn_save.clicked.connect(self.handle_save_auth)
        btn_test = QPushButton("Test Connection")
        btn_test.clicked.connect(self.test_connection)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_test)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        # Status label
        self.auth_status = QLabel("")
        self.auth_status.setStyleSheet("color: green;")
        layout.addWidget(self.auth_status)
        self.tab_auth.setLayout(layout)


    def load_data(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel/CSV file", "", "Excel Files (*.xlsx);;CSV Files (*.csv)")
        if not path:
            return
        try:
            ext = os.path.splitext(path)[1].lower()
            self.data_df = pd.read_csv(path) if ext == '.csv' else pd.read_excel(path)
            self.populate_map_table()
            self.cb_recipient.clear()
            self.cb_recipient.addItem("")
            for col in self.data_df.columns:
                self.cb_recipient.addItem(col)
            for i in range(1, self.cb_recipient.count()):
                if 'email' in self.cb_recipient.itemText(i).lower():
                    self.cb_recipient.setCurrentIndex(i)
                    break
            self.log.append(f"Loaded data: {path} ({len(self.data_df)} rows)")
            self.update_vars_list()
        except Exception as e:
            self.log.append(f"Error loading data: {e}")

    def load_data(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel/CSV file", "",
            "All Excel/CSV Files (*.xlsx *.csv);;Excel Files (*.xlsx);;CSV Files (*.csv)")
        if not path:
            return
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext == '.csv':
                self.data_df = pd.read_csv(path)
            elif ext in ('.xls', '.xlsx'):
                self.data_df = pd.read_excel(path)
            else:
                raise ValueError("Unsupported file type: %s" % ext)
            # Populate mapping table
            self.populate_map_table()
            # Populate recipient combo
            self.cb_recipient.clear()
            self.cb_recipient.addItem("")
            for col in self.data_df.columns:
                self.cb_recipient.addItem(col)
            # Auto-select first 'email' column
            for i in range(1, self.cb_recipient.count()):
                if 'email' in self.cb_recipient.itemText(i).lower():
                    self.cb_recipient.setCurrentIndex(i)
                    break
            # Log
            self.log.append(f"Loaded data: {path} ({len(self.data_df)} rows)")
            # Initialize pagination
            self.current_page = 0
            self.rows_per_page = 5
            self.update_vars_list()
            self.update_data_preview()
        except Exception as e:
            QMessageBox.critical(self, "Load Error", f"Failed to load file: {e}")

    def populate_map_table(self):
        self.map_table.setRowCount(0)
        for col in self.data_df.columns:
            r = self.map_table.rowCount()
            self.map_table.insertRow(r)
            self.map_table.setItem(r, 0, QTableWidgetItem(col))
            default_ph = col.strip().replace(' ', '_').lower()
            le = QLineEdit(default_ph)
            le.textChanged.connect(self.update_vars_list)
            self.map_table.setCellWidget(r, 1, le)

    def update_vars_list(self):
        self.vars_list.clear()
        for r in range(self.map_table.rowCount()):
            ph = self.map_table.cellWidget(r, 1).text().strip().lower()
            if ph:
                self.vars_list.addItem(f"{{{{{ph}}}}}")

    def load_template(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select .docx template", "", "Word Documents (*.docx)")
        if not path:
            return
        self.template_path = path
        self.log.append(f"Loaded data: {path}")
        try:
            with open(path, 'rb') as f:
                html = mammoth.convert_to_html(f).value
            self.preview.setHtml(html)
            self.log.append("Template preview updated.")
        except Exception as e:
            self.log.append(f"Preview error: {e}")
        self.tabs.setCurrentWidget(self.tab_preview)

    def set_zoom(self, factor):
        self.preview.setZoomFactor(self.preview.zoomFactor() * factor)

    def toggle_theme(self):
        if self.chk_dark.isChecked():
            self.setStyleSheet("QWidget{background:#2e2e2e;color:#f0f0f0}")
        else:
            self.setStyleSheet("")

    def handle_save_auth(self):
        self.auth_user = self.auth_email_input.text().strip()
        self.auth_pwd = self.auth_pwd_input.text().strip()
        if not self.auth_user or not self.auth_pwd:
            QMessageBox.warning(self, "Error", "Both email and app password are required.")
            return
        self.save_config()
        QMessageBox.information(self, "Saved", "Credentials saved.")


    def test_connection(self):
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.auth_email_input.text().strip(), self.auth_pwd_input.text().strip())
            server.quit()
            self.auth_status.setText("Connection successful.")
            self.auth_status.setStyleSheet("color: green;")
        except Exception as e:
            self.auth_status.setText(f"Connection failed: {e}")
            self.auth_status.setStyleSheet("color: red;")

    def start_process(self):
        self.tabs.setCurrentWidget(self.tab_run)
        if not self.cb_recipient.currentText():
            QMessageBox.warning(self, "Error", "Please select a recipient email column.")
            return
        subj = self.email_subj.text().strip()
        body = self.email_body.toPlainText().strip()
        fname = self.filename_pattern.text().strip()
        if not subj:
            QMessageBox.warning(self, "Error", "Email subject is required.")
            return
        if not body:
            QMessageBox.warning(self, "Error", "Email body is required.")
            return
        if not fname:
            QMessageBox.warning(self, "Error", "Filename pattern is required.")
            return
        if self.data_df is None or not self.template_path:
            self.log.append("Data or template missing!")
            return
        mapping = {}
        for r in range(self.map_table.rowCount()):
            col = self.map_table.item(r, 0).text()
            ph = self.map_table.cellWidget(r, 1).text().strip().lower()
            if ph:
                mapping[ph] = col
        tpl = DocxTemplate(self.template_path)
        tpl_vars = {var.lower() for var in tpl.get_undeclared_template_variables()}
        wrong_case = [var for var in tpl.get_undeclared_template_variables() if var != var.lower()]
        missing = tpl_vars - set(mapping.keys())
        if wrong_case or missing:
            msg = []
            if wrong_case:
                msg.append("Placeholders not lowercase: " + ", ".join(wrong_case))
            if missing:
                msg.append("Undefined placeholders in template: " + ", ".join(sorted(missing)))
            QMessageBox.critical(self, "Template Error", "\n".join(msg))
            return
        # Validate subject tags
        def find_tags(text): return re.findall(r"\{\{(\w+)\}\}", text)
        invalid_subject = set(find_tags(subj)) - set(mapping.keys())
        invalid_body = set(find_tags(body)) - set(mapping.keys())
        invalid_fname = set(find_tags(fname)) - set(mapping.keys())
        errors = []
        if invalid_subject:
            errors.append("Unknown placeholders in Subject: " + ", ".join(sorted(invalid_subject)))
        if invalid_body:
            errors.append("Unknown placeholders in Body: " + ", ".join(sorted(invalid_body)))
        if invalid_fname:
            errors.append("Unknown placeholders in Filename: " + ", ".join(sorted(invalid_fname)))
        if errors:
            QMessageBox.critical(self, "Tag Error", "\n".join(errors))
            return
        if self.chk_preview.isChecked():
            row0 = self.data_df.iloc[0]
            context0 = {ph: str(row0[col]) for ph, col in mapping.items()}
            tpl.render(context0)
            tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False).name
            tpl.save(tmp)
            pdf0 = os.path.join(os.getcwd(), fname.replace('{{','{').replace('}}','}').format(**context0))
            if not pdf0.lower().endswith('.pdf'):
                pdf0 += '.pdf'
            convert(tmp, pdf0)
            QDesktopServices.openUrl(QUrl.fromLocalFile(pdf0))
            resp = QMessageBox.question(
                self, "Proceed?", "Proceed with emailing certificates?",
                QMessageBox.Yes | QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                self.log.append("Emailing cancelled by user.")
                return
            self.chk_preview.setChecked(False)
        self.handle_save_auth()
        mapping = {self.map_table.cellWidget(r,1).text().strip().lower(): self.map_table.item(r,0).text()
                   for r in range(self.map_table.rowCount()) if self.map_table.cellWidget(r,1).text().strip()}
        recipient_col = self.cb_recipient.currentText()
        subj = self.email_subj.text().strip()
        body = self.email_body.toPlainText().strip()
        fname = self.filename_pattern.text().strip()
        self.thread = QThread()
        self.worker = Worker(
            data_df=self.data_df,
            template_path=self.template_path,
            mapping=mapping,
            recipient_col=recipient_col,
            email_subj=subj,
            email_body=body,
            filename_pattern=fname,
            auth_user=self.auth_user,
            auth_pwd=self.auth_pwd
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.count_updated.connect(
                    lambda proc, tot: self.progress_label.setText(f"{proc}/{tot}"))
        self.worker.progress_updated.connect(self.progress.setValue)
        self.worker.log_message.connect(self.log.append)
        self.worker.finished.connect(lambda s,f: self.on_finished(s,f))
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def on_finished(self, sent, failed):
        """Called when batch processing is done. Writes a CSV of full rows for failures with an error column."""
        self.log.append(f"Done: {sent}/{len(self.data_df)} sent, {len(failed)} failed.")
        if failed:
            import csv
            failed_col = self.cb_recipient.currentText()
            # Prepare CSV with all original columns + error column
            failed_file = os.path.join(APP_DIR, 'failed_list.csv')
            with open(failed_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                # Header: original columns + error
                headers = list(self.data_df.columns) + ['error']
                writer.writerow(headers)
                # For each failure, write matching row(s) with error
                for email, error in failed:
                    rows = self.data_df[self.data_df[failed_col].astype(str) == email]
                    for _, row in rows.iterrows():
                        writer.writerow(list(row.values) + [error])
            self.log.append(f"Exported {os.path.abspath(failed_file)} with full rows and error column.")



if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CertGenerator()
    window.show()
    sys.exit(app.exec_())
"""
Convert PROMPTS.md → PROMPTS.pdf using fpdf2.
Produces a clean, readable PDF with proper formatting.
"""
from fpdf import FPDF
import re, sys, os

MD_PATH = r"D:\Recall\docs\PROMPTS.md"
PDF_PATH = r"D:\Recall\docs\PROMPTS.pdf"

class RecallPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(120, 120, 140)
        self.cell(0, 8, "Recall - Build Prompt Library", align="L")
        self.cell(0, 8, f"Page {self.page_no()}", align="R")
        self.ln(2)
        self.set_draw_color(60, 60, 80)
        self.set_line_width(0.3)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 160)
        self.cell(0, 6, "Recall Confidential - Internal Build Reference", align="C")

    def multi_cell(self, *args, **kwargs):
        if "new_x" not in kwargs:
            kwargs["new_x"] = "LMARGIN"
        if "new_y" not in kwargs:
            kwargs["new_y"] = "NEXT"
        return super().multi_cell(*args, **kwargs)

def sanitize(text):
    """Remove or replace characters fpdf2 can't handle."""
    replacements = {
        "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
        "\u2014": "--", "\u2013": "-", "\u2022": "*", "\u2192": "->",
        "\u2190": "<-", "\u2264": "<=", "\u2265": ">=", "\u00d7": "x",
        "\u00e9": "e", "\u00e8": "e", "\u00e0": "a", "\u00fc": "u",
        "\u03b1": "alpha", "\u03b2": "beta", "\u00b0": "deg",
        "\u2713": "[x]", "\u2610": "[ ]", "\u2611": "[x]",
        "\u2260": "!=", "\u221e": "inf", "\u2248": "~=",
        "\u2705": "[OK]", "\u274c": "[FAIL]", "\u26a0": "[!]",
        "\u00b7": ".", "\u2026": "...", "\u00a0": " ",
        "\u0336": "", "\u200b": "", "\ufeff": "",
        # Box-drawing characters mapped to clean ASCII tree
        "\u251c": "|",
        "\u2514": "+",
        "\u2502": "|",
        "\u2500": "-",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    
    # Strip any remaining characters outside latin-1 block (like emojis)
    cleaned = []
    for char in text:
        try:
            char.encode("latin-1")
            cleaned.append(char)
        except UnicodeEncodeError:
            pass
    return "".join(cleaned)

def make_pdf():
    pdf = RecallPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(12, 18, 12)
    pdf.add_page()

    # Cover page
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(30, 30, 50)
    pdf.ln(20)
    pdf.cell(0, 14, "Recall", align="C")
    pdf.ln(12)
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(80, 80, 100)
    pdf.cell(0, 10, "Build Prompt Library", align="C")
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 11)
    pdf.set_text_color(120, 120, 140)
    pdf.cell(0, 8, "End-to-End Implementation Guide  |  100 Prompts  |  0% to 100%", align="C")
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(160, 160, 170)
    pdf.cell(0, 7, "2026-06-19  |  CONFIDENTIAL  |  D:\\Recall\\docs\\PROMPTS.md", align="C")
    pdf.ln(30)

    # Stats box
    pdf.set_fill_color(240, 240, 248)
    pdf.rect(30, pdf.get_y(), 150, 40, "F")
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(40, 40, 70)
    pdf.ln(6)
    stats = [
        ("100", "Total Prompts"),
        ("18", "Source Documentation Files"),
        ("500+", "Gate Check Items"),
        ("11", "Build Phases"),
    ]
    col_w = 37
    x_start = 32
    for i, (num, label) in enumerate(stats):
        pdf.set_xy(x_start + i * col_w, pdf.get_y() - 2)
        pdf.set_font("Helvetica", "B", 16)
        pdf.set_text_color(60, 60, 120)
        pdf.cell(col_w, 10, num, align="C")
    pdf.ln(8)
    pdf.set_y(pdf.get_y() + 2)
    for i, (num, label) in enumerate(stats):
        pdf.set_xy(x_start + i * col_w, pdf.get_y())
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(110, 110, 130)
        pdf.cell(col_w, 6, label, align="C")
    pdf.ln(14)

    # Now parse and render the markdown
    with open(MD_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    pdf.add_page()

    in_code = False
    code_buffer = []
    gate_check_mode = False

    try:
        for idx, raw_line in enumerate(lines):
            line = raw_line.rstrip("\n")
            s = sanitize(line)

            # Code block toggle
            if s.strip().startswith("```"):
                if in_code:
                    # End of code block — render it
                    in_code = False
                    if code_buffer:
                        pdf.set_font("Courier", "", 7.5)
                        pdf.set_text_color(30, 30, 30)
                        pdf.set_fill_color(245, 245, 250)
                        for cline in code_buffer:
                            pdf.multi_cell(0, 4.2, cline, fill=True, border=0)
                        pdf.ln(2)
                        code_buffer = []
                    gate_check_mode = False
                else:
                    in_code = True
                    lang = s.strip()[3:].strip()
                    gate_check_mode = (lang == "" or lang == "")
                continue

            if in_code:
                code_buffer.append(s if s else "")
                continue

            # Headings
            if s.startswith("# ") and not s.startswith("## "):
                pdf.ln(4)
                pdf.set_font("Helvetica", "B", 16)
                pdf.set_text_color(20, 20, 60)
                pdf.set_fill_color(235, 235, 248)
                pdf.multi_cell(0, 10, s[2:].strip(), fill=True, border=0)
                pdf.set_draw_color(80, 80, 160)
                pdf.set_line_width(0.5)
                pdf.line(12, pdf.get_y(), 198, pdf.get_y())
                pdf.ln(4)
                continue

            if s.startswith("## PROMPT "):
                pdf.ln(5)
                pdf.set_font("Helvetica", "B", 13)
                pdf.set_text_color(40, 40, 120)
                pdf.set_fill_color(228, 230, 250)
                pdf.multi_cell(0, 8, s[3:].strip(), fill=True, border=0)
                pdf.ln(1)
                continue

            if s.startswith("## "):
                pdf.ln(4)
                pdf.set_font("Helvetica", "B", 12)
                pdf.set_text_color(50, 50, 130)
                pdf.set_fill_color(232, 232, 248)
                pdf.multi_cell(0, 7, s[3:].strip(), fill=True, border=0)
                pdf.ln(2)
                continue

            if s.startswith("### "):
                pdf.ln(2)
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(70, 70, 140)
                pdf.multi_cell(0, 6, s[4:].strip())
                pdf.ln(1)
                continue

            if s.startswith("#### "):
                pdf.set_font("Helvetica", "BI", 9)
                pdf.set_text_color(90, 90, 150)
                pdf.multi_cell(0, 5.5, s[5:].strip())
                continue

            # Horizontal rule
            if s.strip() == "---":
                pdf.ln(2)
                pdf.set_draw_color(180, 180, 200)
                pdf.set_line_width(0.3)
                pdf.line(12, pdf.get_y(), 198, pdf.get_y())
                pdf.ln(3)
                continue

            # Skills line (bold label)
            if s.startswith("**Skills:**"):
                pdf.set_font("Helvetica", "B", 8.5)
                pdf.set_text_color(100, 60, 180)
                skills_text = s.replace("**Skills:**", "SKILLS:").replace("`", "").replace("**", "")
                pdf.multi_cell(0, 5, skills_text.strip())
                pdf.ln(1)
                continue

            # Gate Check items
            if "[ ]" in s or "[x]" in s or "[/]" in s:
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(40, 120, 40)
                clean = s.strip().replace("[ ]", "->").replace("[x]", "[X]").replace("[/]", "[~]")
                pdf.multi_cell(0, 5, "  " + clean)
                continue

            # Table rows
            if s.strip().startswith("|"):
                pdf.set_font("Courier", "", 7)
                pdf.set_text_color(30, 30, 60)
                # Clean markdown table pipes
                cells = [c.strip() for c in s.strip().strip("|").split("|")]
                if all(set(c.strip()) <= set("-: ") for c in cells):
                    continue  # skip separator row
                row_text = "  |  ".join(c[:35] for c in cells[:5])
                pdf.multi_cell(0, 4.5, row_text)
                continue

            # Bold line (prompt sub-headers, gate check header)
            if s.strip().startswith("**") and s.strip().endswith("**"):
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(50, 50, 80)
                pdf.multi_cell(0, 5.5, s.strip().replace("**", ""))
                pdf.ln(0.5)
                continue

            # Bullet points
            if s.strip().startswith("- ") or s.strip().startswith("* "):
                pdf.set_font("Helvetica", "", 8.5)
                pdf.set_text_color(40, 40, 60)
                indent = len(s) - len(s.lstrip())
                bullet = "  " * (indent // 2) + "- " + s.strip()[2:]
                pdf.multi_cell(0, 5, bullet)
                continue

            # Regular text
            if s.strip():
                # Remove inline markdown
                clean = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
                clean = re.sub(r"\*(.+?)\*", r"\1", clean)
                clean = re.sub(r"`(.+?)`", r"\1", clean)
                clean = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", clean)
                pdf.set_font("Helvetica", "", 8.5)
                pdf.set_text_color(40, 40, 60)
                if len(clean.strip()) > 0:
                    pdf.multi_cell(0, 5, clean.strip())
            else:
                pdf.ln(2)
    except Exception as e:
        print(f"Error occurred at line {idx+1} in PROMPTS.md:")
        print(f"Content: {repr(raw_line)}")
        print(f"Current PDF state: page={pdf.page_no()}, x={pdf.get_x()}, y={pdf.get_y()}")
        raise e

    pdf.output(PDF_PATH)
    print(f"PDF created: {PDF_PATH}")
    size_kb = os.path.getsize(PDF_PATH) // 1024
    pages = pdf.page
    print(f"Size: {size_kb} KB  |  Pages: {pages}")

if __name__ == "__main__":
    make_pdf()


import pymupdf
import pytesseract
from PIL import Image
from pathlib import Path
import io

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

base_dir = Path(__file__).resolve().parent
pdf_path = base_dir / "sample_pdfs" / "sample_pitch_deck.pdf"
output_path = base_dir / "extracted_text.txt"

if not pdf_path.exists():
    print("PDF file not found:", pdf_path)
    exit()

document = pymupdf.open(pdf_path)

extracted_text = ""

for page_number, page in enumerate(document, start=1):
    pix = page.get_pixmap(
        matrix=pymupdf.Matrix(2, 2),
        alpha=False
    )

    image = Image.open(io.BytesIO(pix.tobytes("png")))

    text = pytesseract.image_to_string(
        image,
        lang="eng"
    )

    extracted_text += text + "\n"

    print(f"Processed page {page_number}/{len(document)}")

document.close()

output_path.write_text(
    extracted_text,
    encoding="utf-8"
)

print("\nTotal characters extracted:", len(extracted_text))
print("\n========== EXTRACTED TEXT ==========\n")
print(extracted_text[:5000])

print("\nText saved successfully to:", output_path)

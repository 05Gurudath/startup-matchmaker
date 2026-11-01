
import re
import uuid
import io
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image
import chromadb
from chromadb.utils import embedding_functions

from backend.database import get_db_connection

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
CHROMA_DIR = BASE_DIR / "chroma_db"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

CHUNK_SIZE = 120
CHUNK_OVERLAP = 25

HEADINGS = [
    "Welcome",
    "Problem",
    "Solution",
    "Product",
    "Business Model",
    "Market Validation",
    "Market Size",
    "Market",
    "Adoption Strategy",
    "Competition",
    "Competitive Advantages",
    "Team",
    "Press",
    "Testimonials",
    "Financial",
    "Financials"
]


def extract_pdf_text(pdf_path):
    document = pymupdf.open(pdf_path)
    extracted_text = ""

    try:
        for page_number, page in enumerate(document, start=1):
            pix = page.get_pixmap(
                matrix=pymupdf.Matrix(2, 2),
                alpha=False
            )

            image = Image.open(
                io.BytesIO(pix.tobytes("png"))
            )

            text = pytesseract.image_to_string(
                image,
                lang="eng"
            )

            extracted_text += text + "\n"
            print(f"Processed page {page_number}/{len(document)}")

    finally:
        document.close()

    return extracted_text


def normalize_line(line):
    line = line.strip()
    line = re.sub(r"\s+", " ", line)
    line = re.sub(r"[|]+", " ", line)
    return line.strip(" -_•")


def detect_heading(line):
    normalized = normalize_line(line)

    for heading in sorted(HEADINGS, key=len, reverse=True):
        pattern = rf"^{re.escape(heading)}(?:\s+\d+)?$"

        if re.fullmatch(pattern, normalized, re.IGNORECASE):
            return heading

    return None


def extract_sections(text):
    sections = {"Introduction": []}
    current_section = "Introduction"

    for raw_line in text.splitlines():
        line = normalize_line(raw_line)

        if not line:
            continue

        heading = detect_heading(line)

        if heading:
            current_section = heading

            if current_section not in sections:
                sections[current_section] = []

            continue

        sections[current_section].append(line)

    cleaned_sections = {}

    for section, lines in sections.items():
        content = " ".join(lines)
        content = re.sub(r"\s+", " ", content).strip()

        if content:
            cleaned_sections[section] = content

    return cleaned_sections


def create_chunks(sections):
    chunks = []

    for section, content in sections.items():
        words = content.split()
        start = 0
        chunk_number = 1

        while start < len(words):
            end = start + CHUNK_SIZE
            chunk_text = " ".join(words[start:end])

            if chunk_text.strip():
                chunks.append({
                    "text": chunk_text,
                    "section": section,
                    "chunk_number": chunk_number
                })

            if end >= len(words):
                break

            start = end - CHUNK_OVERLAP
            chunk_number += 1

    return chunks


def get_collection():
    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR)
    )

    embedding_function = (
        embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    )

    return client.get_or_create_collection(
        name="pitch_deck_chunks",
        embedding_function=embedding_function,
        metadata={
            "description": "Section-aware startup pitch deck chunks"
        }
    )


def process_pitch_deck(pdf_path, startup_id):
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                s.startup_id,
                s.name,
                s.industry_id,
                i.industry_name
            FROM startups s
            JOIN industries i
                ON s.industry_id = i.industry_id
            WHERE s.startup_id = %s
            """,
            (startup_id,)
        )

        startup = cursor.fetchone()

        if not startup:
            raise ValueError("Startup not found")

        extracted_text = extract_pdf_text(pdf_path)

        if not extracted_text.strip():
            raise ValueError("No text could be extracted from the PDF")

        sections = extract_sections(extracted_text)
        chunks = create_chunks(sections)

        if not chunks:
            raise ValueError("No pitch deck sections were identified")

        file_path = Path(pdf_path)
        file_name = file_path.name

        cursor.execute(
            """
            INSERT INTO pitch_decks
                (startup_id, file_name, file_type,
                 upload_date, version, analysis_status)
            VALUES (%s, %s, %s, NOW(), %s, %s)
            """,
            (
                startup_id,
                file_name,
                "PDF",
                "v1.0",
                "Analyzed"
            )
        )

        mysql_deck_id = cursor.lastrowid

        collection = get_collection()

        documents = []
        ids = []
        metadatas = []

        upload_id = uuid.uuid4().hex

        for index, chunk in enumerate(chunks):
            documents.append(chunk["text"])

            ids.append(
                f"startup_{startup_id}_deck_{mysql_deck_id}_{upload_id}_{index}"
            )

            metadatas.append({
                "startup_name": startup["name"],
                "industry": startup["industry_name"],
                "deck_id": str(mysql_deck_id),
                "mysql_startup_id": int(startup_id),
                "mysql_deck_id": int(mysql_deck_id),
                "section": chunk["section"],
                "chunk_number": int(chunk["chunk_number"])
            })

        collection.add(
            documents=documents,
            ids=ids,
            metadatas=metadatas
        )

        connection.commit()

        return {
            "message": "Pitch deck processed successfully",
            "startup_id": startup_id,
            "startup_name": startup["name"],
            "deck_id": mysql_deck_id,
            "file_name": file_name,
            "total_characters": len(extracted_text),
            "sections_identified": {
                section: len(content.split())
                for section, content in sections.items()
            },
            "total_chunks": len(chunks),
            "chroma_collection": "pitch_deck_chunks"
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()

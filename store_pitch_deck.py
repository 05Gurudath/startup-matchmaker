
import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

BASE_DIR = Path(__file__).resolve().parent
TEXT_FILE = BASE_DIR / "extracted_text.txt"
CHROMA_DIR = BASE_DIR / "chroma_db"

STARTUP_NAME = "Airbnb"
INDUSTRY = "TravelTech"
DECK_ID = "airbnb_deck_001"
MYSQL_STARTUP_ID = 6
MYSQL_DECK_ID = 6

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

TEST_SECTIONS = [
    "Business Model",
    "Market Validation",
    "Market Size",
    "Competition",
    "Competitive Advantages",
    "Adoption Strategy",
    "Financial"
]


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
    sections = {}
    current_section = "Introduction"
    sections[current_section] = []

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

        if not words:
            continue

        start = 0
        chunk_number = 1

        while start < len(words):
            end = start + CHUNK_SIZE
            chunk_words = words[start:end]
            chunk_text = " ".join(chunk_words)

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


def create_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    try:
        client.delete_collection("pitch_deck_chunks")
    except Exception:
        pass

    collection = client.create_collection(
        name="pitch_deck_chunks",
        embedding_function=embedding_function,
        metadata={"description": "Section-aware Airbnb pitch deck chunks"}
    )

    return collection


def store_chunks(collection, chunks):
    documents = []
    ids = []
    metadatas = []

    for index, chunk in enumerate(chunks):
        documents.append(chunk["text"])
        ids.append(f"airbnb_chunk_{index + 1}")

        metadatas.append({
            "startup_name": STARTUP_NAME,
            "industry": INDUSTRY,
            "deck_id": DECK_ID,
            "mysql_startup_id": MYSQL_STARTUP_ID,
            "mysql_deck_id": MYSQL_DECK_ID,
            "section": chunk["section"],
            "chunk_number": chunk["chunk_number"]
        })

    if documents:
        collection.add(
            documents=documents,
            ids=ids,
            metadatas=metadatas
        )

    return len(documents)


def test_section_search(collection):
    print("\n========== SECTION SEARCH TEST ==========")

    queries = {
        "Business Model": "How does the startup make money?",
        "Market Validation": "What evidence supports the market opportunity?",
        "Market Size": "What is the total available market and market size?",
        "Competition": "Who are the competitors?",
        "Competitive Advantages": "What advantages make this startup different?",
        "Adoption Strategy": "How will the startup acquire customers and grow?",
        "Financial": "What are the financial projections and funding requirements?"
    }

    for section, query in queries.items():
        print(f"\nTopic: {section}")

        results = collection.query(
            query_texts=[query],
            n_results=2,
            where={
                "$and": [
                    {"mysql_startup_id": MYSQL_STARTUP_ID},
                    {"section": section}
                ]
            },
            include=["documents", "distances", "metadatas"]
        )

        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        if not documents:
            print("No content found for this section.")
            continue

        for document, distance, metadata in zip(
            documents, distances, metadatas
        ):
            print(f"Section: {metadata['section']}")
            print(f"Chunk: {metadata['chunk_number']}")
            print(f"Distance: {distance:.4f}")
            print(f"Content: {document[:900]}")


def main():
    print("Reading extracted pitch deck text...")

    if not TEXT_FILE.exists():
        print(f"ERROR: File not found: {TEXT_FILE}")
        return

    text = TEXT_FILE.read_text(encoding="utf-8", errors="replace")

    sections = extract_sections(text)

    print(f"\nSections identified: {len(sections)}")

    for section, content in sections.items():
        print(f"- {section} ({len(content.split())} words)")

    chunks = create_chunks(sections)

    print(f"\nTotal chunks created: {len(chunks)}")

    if not chunks:
        print("ERROR: No chunks were created.")
        return

    collection = create_collection()

    total_stored = store_chunks(collection, chunks)

    print("\nChromaDB collection rebuilt successfully!")
    print(f"Total stored chunks: {total_stored}")

    test_section_search(collection)

    print("\n========== PROCESSING COMPLETED ==========")


if __name__ == "__main__":
    main()

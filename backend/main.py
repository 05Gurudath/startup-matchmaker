
import uuid
from pathlib import Path

import chromadb

from fastapi import (
    FastAPI,
    HTTPException,
    UploadFile,
    File,
    Form,
    Depends
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from backend.database import get_db_connection
from backend.pitch_service import process_pitch_deck, UPLOAD_DIR
from backend.auth import (
    verify_password,
    create_access_token,
    get_current_user
)

from matching_engine import generate_matches_api


# ---------------- CONFIGURATION ----------------

BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_PATH = BASE_DIR / "chroma_db"
COLLECTION_NAME = "pitch_deck_chunks"


app = FastAPI(
    title="Startup Pitch Deck Analyzer",
    description="API for startup analysis and investor matching",
    version="1.3.0"
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ---------------- REQUEST MODELS ----------------

class LoginRequest(BaseModel):
    email: str
    password: str


# ---------------- CHROMADB ----------------

def get_chroma_collection():
    client = chromadb.PersistentClient(
        path=str(CHROMA_PATH)
    )

    return client.get_collection(
        name=COLLECTION_NAME
    )


# ---------------- ROLE AND OWNERSHIP CHECKS ----------------

def verify_startup_access(startup_id: int, user: dict):

    # Admin can access every startup.
    if user["role"] == "Admin":
        return

    # Only Startup accounts can access private startup data.
    if user["role"] != "Startup":
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to access this resource"
        )

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT startup_id
            FROM startups
            WHERE startup_id = %s
            AND user_id = %s
            """,
            (startup_id, user["user_id"])
        )

        if not cursor.fetchone():
            raise HTTPException(
                status_code=403,
                detail="You can only access your own startup"
            )

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()


# ---------------- HOME AND HEALTH ----------------

@app.get("/")
def home():
    return {
        "message": "Startup Pitch Deck Analyzer API is running"
    }


@app.get("/health")
def health_check():

    connection = None

    try:
        connection = get_db_connection()

        return {
            "status": "healthy",
            "database": "connected"
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Database connection failed"
        )

    finally:
        if connection and connection.is_connected():
            connection.close()


# ---------------- AUTHENTICATION ----------------

@app.post("/auth/login")
def login(request: LoginRequest):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT user_id, name, email, password_hash, role
            FROM users
            WHERE email = %s
            """,
            (request.email.strip().lower(),)
        )

        user = cursor.fetchone()

        if not user or not verify_password(
            request.password,
            user["password_hash"]
        ):
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password"
            )

        token = create_access_token(user)

        return {
            "message": "Login successful",
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "user_id": user["user_id"],
                "name": user["name"],
                "email": user["email"],
                "role": user["role"]
            }
        }

    finally:
        cursor.close()
        connection.close()


@app.get("/auth/me")
def get_logged_in_user(
    user: dict = Depends(get_current_user)
):
    return {
        "user": user
    }


# ---------------- STARTUPS ----------------

@app.get("/startups")
def get_startups(
    user: dict = Depends(get_current_user)
):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                s.startup_id,
                s.name,
                s.description,
                s.stage,
                s.location,
                s.funding_required,
                s.founded_year,
                i.industry_name
            FROM startups s
            JOIN industries i
                ON s.industry_id = i.industry_id
            ORDER BY s.startup_id
            """
        )

        return {
            "startups": cursor.fetchall()
        }

    except Exception as error:
        print("Startup retrieval error:", error)

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve startups"
        )

    finally:
        cursor.close()
        connection.close()


@app.get("/startups/{startup_id}")
def get_startup(
    startup_id: int,
    user: dict = Depends(get_current_user)
):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                s.startup_id,
                s.name,
                s.description,
                s.stage,
                s.location,
                s.funding_required,
                s.founded_year,
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
            raise HTTPException(
                status_code=404,
                detail="Startup not found"
            )

        return startup

    finally:
        cursor.close()
        connection.close()


# ---------------- INVESTORS ----------------

@app.get("/investors")
def get_investors(
    user: dict = Depends(get_current_user)
):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                investor_id,
                name,
                organization,
                investor_type,
                location,
                min_investment,
                max_investment,
                website
            FROM investors
            ORDER BY investor_id
            """
        )

        return {
            "investors": cursor.fetchall()
        }

    except Exception as error:
        print("Investor retrieval error:", error)

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve investors"
        )

    finally:
        cursor.close()
        connection.close()


# ---------------- PITCH DECKS ----------------

@app.get("/pitch-decks/{startup_id}")
def get_pitch_decks(
    startup_id: int,
    user: dict = Depends(get_current_user)
):

    verify_startup_access(startup_id, user)

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                deck_id,
                startup_id,
                file_name,
                file_type,
                upload_date,
                version,
                analysis_status
            FROM pitch_decks
            WHERE startup_id = %s
            ORDER BY upload_date DESC, deck_id DESC
            """,
            (startup_id,)
        )

        decks = cursor.fetchall()

        return {
            "startup_id": startup_id,
            "total_decks": len(decks),
            "pitch_decks": decks
        }

    except Exception as error:
        print("Pitch deck retrieval error:", error)

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve pitch decks"
        )

    finally:
        cursor.close()
        connection.close()


@app.get("/pitch-decks/{startup_id}/latest")
def get_latest_pitch_deck(
    startup_id: int,
    user: dict = Depends(get_current_user)
):

    verify_startup_access(startup_id, user)

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                deck_id,
                startup_id,
                file_name,
                file_type,
                upload_date,
                version,
                analysis_status
            FROM pitch_decks
            WHERE startup_id = %s
            ORDER BY upload_date DESC, deck_id DESC
            LIMIT 1
            """,
            (startup_id,)
        )

        deck = cursor.fetchone()

        if not deck:
            raise HTTPException(
                status_code=404,
                detail="No pitch deck found for this startup"
            )

        return deck

    finally:
        cursor.close()
        connection.close()


@app.get("/pitch-decks/{startup_id}/analysis/{deck_id}")
def get_pitch_deck_analysis(
    startup_id: int,
    deck_id: int,
    user: dict = Depends(get_current_user)
):

    verify_startup_access(startup_id, user)

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                deck_id,
                startup_id,
                file_name,
                file_type,
                upload_date,
                version,
                analysis_status
            FROM pitch_decks
            WHERE startup_id = %s AND deck_id = %s
            """,
            (startup_id, deck_id)
        )

        deck = cursor.fetchone()

        if not deck:
            raise HTTPException(
                status_code=404,
                detail="Pitch deck not found"
            )

    finally:
        cursor.close()
        connection.close()

    try:
        collection = get_chroma_collection()

        result = collection.get(
            where={
                "mysql_deck_id": deck_id
            },
            include=[
                "documents",
                "metadatas"
            ]
        )

        chunks = []

        for index, document in enumerate(
            result["documents"] or []
        ):
            metadata = (result["metadatas"] or [])[index]

            chunks.append({
                "content": document,
                "section": metadata.get("section", "General"),
                "chunk_number": metadata.get("chunk_number"),
                "startup_id": metadata.get("mysql_startup_id"),
                "deck_id": metadata.get("mysql_deck_id")
            })

        sections = sorted({
            chunk["section"]
            for chunk in chunks
        })

        return {
            "deck": deck,
            "total_chunks": len(chunks),
            "total_sections": len(sections),
            "sections": sections,
            "chunks": chunks
        }

    except Exception as error:
        print("ChromaDB analysis retrieval error:", error)

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve pitch deck analysis from ChromaDB"
        )


# ---------------- INVESTOR MATCHING ----------------

@app.get("/matches/{startup_id}")
def get_matches(
    startup_id: int,
    user: dict = Depends(get_current_user)
):

    verify_startup_access(startup_id, user)

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                m.match_id,
                m.startup_id,
                m.investor_id,
                i.name AS investor_name,
                i.organization,
                i.investor_type,
                m.match_score,
                m.industry_score,
                m.stage_score,
                m.investment_score,
                m.location_score,
                m.similarity_score,
                m.generated_at
            FROM match_results m
            JOIN investors i
                ON m.investor_id = i.investor_id
            WHERE m.startup_id = %s
            ORDER BY m.match_score DESC
            """,
            (startup_id,)
        )

        matches = cursor.fetchall()

        return {
            "startup_id": startup_id,
            "total_matches": len(matches),
            "matches": matches
        }

    except Exception as error:
        print("Match retrieval error:", error)

        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve matching results"
        )

    finally:
        cursor.close()
        connection.close()


# ---------------- UPLOAD PITCH DECK ----------------

@app.post("/upload-pitch-deck")
async def upload_pitch_deck(
    startup_id: int = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):

    verify_startup_access(startup_id, user)

    if startup_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid startup ID"
        )

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Filename is required"
        )

    if Path(file.filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )

    file_id = uuid.uuid4().hex
    safe_filename = f"{file_id}.pdf"

    startup_dir = UPLOAD_DIR / f"startup_{startup_id}"
    startup_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    file_path = startup_dir / safe_filename

    try:
        content = await file.read()

        if not content:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty"
            )

        if len(content) > 15 * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail="PDF must be 15 MB or smaller"
            )

        if not content.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=400,
                detail="Invalid PDF file"
            )

        file_path.write_bytes(content)

        result = await run_in_threadpool(
            process_pitch_deck,
            file_path,
            startup_id
        )

        return result

    except HTTPException:
        if file_path.exists():
            file_path.unlink()

        raise

    except ValueError as error:
        if file_path.exists():
            file_path.unlink()

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:
        if file_path.exists():
            file_path.unlink()

        print("Pitch deck processing error:", error)

        raise HTTPException(
            status_code=500,
            detail="Pitch deck processing failed. Check the backend terminal."
        )

    finally:
        await file.close()


# ---------------- GENERATE MATCHES ----------------

@app.post("/generate-matches/{startup_id}")
async def generate_matches(
    startup_id: int,
    user: dict = Depends(get_current_user)
):

    verify_startup_access(startup_id, user)

    if startup_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="Invalid startup ID"
        )

    try:
        result = await run_in_threadpool(
            generate_matches_api,
            startup_id
        )

        return result

    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error)
        )

    except Exception as error:
        print("Investor matching error:", error)

        raise HTTPException(
            status_code=500,
            detail="Investor matching failed. Check the backend terminal."
        )

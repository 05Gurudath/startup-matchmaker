import sys
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from backend.database import get_db_connection


BASE_DIR = Path(__file__).resolve().parent
CHROMA_PATH = str(BASE_DIR / "chroma_db")
COLLECTION_NAME = "pitch_deck_chunks"

WEIGHTS = {
    "industry": 30,
    "stage": 20,
    "investment": 20,
    "location": 10,
    "similarity": 20
}

EVIDENCE_SECTIONS = {
    "Business Model": "How does the startup generate revenue?",
    "Market Validation": "What evidence validates the market?",
    "Market Size": "What is the market size and opportunity?",
    "Competition": "Who are the competitors?",
    "Competitive Advantages": "What are the startup's competitive advantages?",
    "Adoption Strategy": "How will the startup acquire customers?",
    "Financial": "What are the startup's financial projections and funding requirements?"
}


def connect_mysql():
    return get_db_connection()


def connect_chromadb():
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    embedding_function = (
        embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    )

    return client.get_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function
    )


def get_startup(connection, startup_id):
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                s.startup_id,
                s.name AS startup_name,
                s.description,
                s.stage,
                s.location,
                s.funding_required,
                s.founded_year,
                i.industry_id,
                i.industry_name
            FROM startups s
            JOIN industries i ON s.industry_id = i.industry_id
            WHERE s.startup_id = %s
            """,
            (startup_id,)
        )

        return cursor.fetchone()

    finally:
        cursor.close()


def get_investor_preferences(connection):
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                i.investor_id,
                i.name AS investor_name,
                i.organization,
                i.investor_type,
                i.location AS investor_location,
                i.min_investment,
                i.max_investment,
                p.preference_id,
                p.industry_id AS preferred_industry_id,
                ind.industry_name AS preferred_industry,
                p.preferred_stage,
                p.min_check_size,
                p.max_check_size,
                p.preferred_location
            FROM investors i
            JOIN investor_preferences p
                ON i.investor_id = p.investor_id
            JOIN industries ind
                ON p.industry_id = ind.industry_id
            ORDER BY i.investor_id, p.preference_id
            """
        )

        return cursor.fetchall()

    finally:
        cursor.close()


def get_latest_deck(connection, startup_id):
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            """
            SELECT
                deck_id,
                file_name,
                upload_date,
                analysis_status
            FROM pitch_decks
            WHERE startup_id = %s
            ORDER BY upload_date DESC, deck_id DESC
            LIMIT 1
            """,
            (startup_id,)
        )

        return cursor.fetchone()

    finally:
        cursor.close()


def retrieve_pitch_evidence(collection, startup_id, deck_id):
    evidence = {}

    for section, query in EVIDENCE_SECTIONS.items():
        results = collection.query(
            query_texts=[query],
            n_results=2,
            where={
                "$and": [
                    {"mysql_startup_id": int(startup_id)},
                    {"mysql_deck_id": int(deck_id)},
                    {"section": section}
                ]
            },
            include=["documents", "distances", "metadatas"]
        )

        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]

        evidence[section] = []

        for document, distance, metadata in zip(
            documents, distances, metadatas
        ):
            evidence[section].append({
                "content": document,
                "distance": float(distance),
                "chunk_number": metadata.get("chunk_number")
            })

    return evidence


def build_investor_query(preference):
    return (
        f"Investor investment thesis for "
        f"{preference['preferred_industry']} startups. "
        f"Preferred startup stage: {preference['preferred_stage']}. "
        f"Preferred investment location: "
        f"{preference['preferred_location'] or 'Not specified'}. "
        f"Investor type: {preference['investor_type'] or 'Not specified'}. "
        f"Organization: {preference['organization'] or 'Not specified'}. "
        "The investor is interested in startup business models, "
        "market opportunity, validation, competitive advantage, "
        "customer adoption strategy, and financial projections."
    )


def distance_to_similarity(distance):
    distance = max(float(distance), 0.0)
    return round((1 / (1 + distance)) * 100, 2)


def calculate_semantic_similarity(
    collection,
    startup_id,
    deck_id,
    preference
):
    query = build_investor_query(preference)

    results = collection.query(
        query_texts=[query],
        n_results=5,
        where={
            "$and": [
                {"mysql_startup_id": int(startup_id)},
                {"mysql_deck_id": int(deck_id)}
            ]
        },
        include=["documents", "distances", "metadatas"]
    )

    documents = results.get("documents", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    if not distances:
        return None, []

    similarities = [
        distance_to_similarity(distance)
        for distance in distances
    ]

    semantic_score = round(
        sum(similarities) / len(similarities), 2
    )

    matched_chunks = []

    for document, distance, metadata, similarity in zip(
        documents, distances, metadatas, similarities
    ):
        matched_chunks.append({
            "content": document,
            "distance": round(float(distance), 4),
            "similarity": similarity,
            "section": metadata.get("section"),
            "chunk_number": metadata.get("chunk_number")
        })

    return semantic_score, matched_chunks


def calculate_dimension_scores(
    startup,
    preference,
    semantic_score
):
    scores = {}

    scores["industry"] = (
        100
        if startup["industry_id"]
        == preference["preferred_industry_id"]
        else 0
    )

    scores["stage"] = (
        100
        if (startup["stage"] or "").strip().lower()
        == (preference["preferred_stage"] or "").strip().lower()
        else 0
    )

    funding = startup["funding_required"]
    minimum = preference["min_check_size"]
    maximum = preference["max_check_size"]

    if funding is None or minimum is None or maximum is None:
        scores["investment"] = None
    else:
        scores["investment"] = (
            100 if minimum <= funding <= maximum else 0
        )

    startup_location = (
        startup["location"] or ""
    ).strip().lower()

    preferred_location = (
        preference["preferred_location"] or ""
    ).strip().lower()

    if not startup_location or not preferred_location:
        scores["location"] = None
    else:
        scores["location"] = (
            100
            if startup_location == preferred_location
            else 0
        )

    scores["similarity"] = semantic_score

    return scores


def calculate_match_score(scores):
    available_weight = sum(
        WEIGHTS[key]
        for key, value in scores.items()
        if value is not None
    )

    if available_weight == 0:
        return None, 0

    weighted_total = sum(
        scores[key] * WEIGHTS[key]
        for key in WEIGHTS
        if scores.get(key) is not None
    )

    match_score = round(
        weighted_total / available_weight, 2
    )

    return match_score, available_weight


def explain_match(startup, preference, scores):
    explanations = []

    if scores["industry"] == 100:
        explanations.append(
            f"Industry matches: {startup['industry_name']}"
        )
    else:
        explanations.append(
            f"Industry mismatch: startup is "
            f"{startup['industry_name']}, investor prefers "
            f"{preference['preferred_industry']}"
        )

    if scores["stage"] == 100:
        explanations.append(
            f"Stage matches: {startup['stage']}"
        )
    else:
        explanations.append(
            f"Stage mismatch: startup is {startup['stage']}, "
            f"investor prefers {preference['preferred_stage']}"
        )

    if scores["investment"] is None:
        explanations.append(
            "Investment compatibility unavailable: "
            "funding requirement or investor check-size range is missing"
        )
    elif scores["investment"] == 100:
        explanations.append(
            "Funding requirement is within investor's preferred range"
        )
    else:
        explanations.append(
            "Funding requirement is outside investor's preferred range"
        )

    if scores["location"] is None:
        explanations.append(
            "Location compatibility unavailable"
        )
    elif scores["location"] == 100:
        explanations.append(
            "Location matches investor preference"
        )
    else:
        explanations.append(
            f"Location mismatch: startup is {startup['location']}, "
            f"investor prefers {preference['preferred_location']}"
        )

    if scores["similarity"] is None:
        explanations.append(
            "Semantic similarity unavailable: no pitch chunks found"
        )
    else:
        explanations.append(
            f"Pitch deck semantic relevance: "
            f"{scores['similarity']:.2f}/100"
        )

    return explanations


def rank_investors(
    startup,
    preferences,
    collection,
    deck_id
):
    investor_results = {}

    for preference in preferences:

        semantic_score, matched_chunks = (
            calculate_semantic_similarity(
                collection,
                startup["startup_id"],
                deck_id,
                preference
            )
        )

        scores = calculate_dimension_scores(
            startup,
            preference,
            semantic_score
        )

        match_score, coverage = calculate_match_score(scores)

        result = {
            "investor_id": preference["investor_id"],
            "investor_name": preference["investor_name"],
            "organization": preference["organization"],
            "investor_type": preference["investor_type"],
            "scores": scores,
            "match_score": match_score,
            "coverage": coverage,
            "matched_pitch_chunks": matched_chunks,
            "explanations": explain_match(
                startup,
                preference,
                scores
            )
        }

        investor_id = preference["investor_id"]
        previous = investor_results.get(investor_id)

        if (
            previous is None
            or (
                match_score is not None
                and (
                    previous["match_score"] is None
                    or match_score > previous["match_score"]
                )
            )
        ):
            investor_results[investor_id] = result

    return sorted(
        investor_results.values(),
        key=lambda result: (
            result["match_score"] is not None,
            result["match_score"] or 0,
            result["coverage"]
        ),
        reverse=True
    )


def save_results(connection, startup_id, rankings):
    cursor = connection.cursor()

    inserted_count = 0
    updated_count = 0

    try:
        for investor in rankings:

            if investor["match_score"] is None:
                continue

            scores = investor["scores"]

            cursor.execute(
                """
                SELECT match_id
                FROM match_results
                WHERE startup_id = %s
                AND investor_id = %s
                ORDER BY generated_at DESC, match_id DESC
                LIMIT 1
                """,
                (
                    startup_id,
                    investor["investor_id"]
                )
            )

            existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    """
                    UPDATE match_results
                    SET
                        match_score = %s,
                        industry_score = %s,
                        stage_score = %s,
                        investment_score = %s,
                        location_score = %s,
                        similarity_score = %s,
                        generated_at = CURRENT_TIMESTAMP
                    WHERE match_id = %s
                    """,
                    (
                        investor["match_score"],
                        scores["industry"],
                        scores["stage"],
                        scores["investment"],
                        scores["location"],
                        scores["similarity"],
                        existing[0]
                    )
                )

                updated_count += 1

            else:
                cursor.execute(
                    """
                    INSERT INTO match_results (
                        startup_id,
                        investor_id,
                        match_score,
                        industry_score,
                        stage_score,
                        investment_score,
                        location_score,
                        similarity_score
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        startup_id,
                        investor["investor_id"],
                        investor["match_score"],
                        scores["industry"],
                        scores["stage"],
                        scores["investment"],
                        scores["location"],
                        scores["similarity"]
                    )
                )

                inserted_count += 1

        connection.commit()

        return inserted_count, updated_count

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()


def build_api_rankings(rankings):
    results = []

    for index, investor in enumerate(rankings):

        results.append({
            "rank": index + 1,
            "investor_id": investor["investor_id"],
            "investor_name": investor["investor_name"],
            "organization": investor["organization"],
            "investor_type": investor["investor_type"],
            "match_score": investor["match_score"],
            "data_coverage": investor["coverage"],
            "dimension_scores": {
                "industry": investor["scores"]["industry"],
                "stage": investor["scores"]["stage"],
                "investment": investor["scores"]["investment"],
                "location": investor["scores"]["location"],
                "semantic_similarity": investor["scores"]["similarity"]
            },
            "matched_pitch_chunks": investor["matched_pitch_chunks"],
            "explanations": investor["explanations"]
        })

    return results


def generate_matches_api(startup_id):
    connection = get_db_connection()

    try:
        startup = get_startup(connection, startup_id)

        if not startup:
            raise ValueError("Startup not found")

        latest_deck = get_latest_deck(
            connection,
            startup_id
        )

        if not latest_deck:
            raise ValueError(
                "No pitch deck uploaded for this startup"
            )

        preferences = get_investor_preferences(connection)

        if not preferences:
            raise ValueError(
                "No investor preferences found"
            )

        collection = connect_chromadb()

        evidence = retrieve_pitch_evidence(
            collection,
            startup_id,
            latest_deck["deck_id"]
        )

        rankings = rank_investors(
            startup,
            preferences,
            collection,
            latest_deck["deck_id"]
        )

        inserted_count, updated_count = save_results(
            connection,
            startup_id,
            rankings
        )

        return {
            "message": "Investor matching completed",
            "startup": {
                "startup_id": startup["startup_id"],
                "name": startup["startup_name"],
                "industry": startup["industry_name"],
                "stage": startup["stage"],
                "location": startup["location"]
            },
            "latest_pitch_deck": {
                "deck_id": latest_deck["deck_id"],
                "file_name": latest_deck["file_name"],
                "analysis_status": latest_deck["analysis_status"]
            },
            "pitch_deck_evidence": evidence,
            "total_investors": len(rankings),
            "matches_inserted": inserted_count,
            "matches_updated": updated_count,
            "rankings": build_api_rankings(rankings)
        }

    finally:
        connection.close()


def run_matching(startup_id, save=False):
    connection = None

    try:
        connection = connect_mysql()

        startup = get_startup(
            connection,
            startup_id
        )

        if not startup:
            print(f"Startup ID {startup_id} not found.")
            return

        latest_deck = get_latest_deck(
            connection,
            startup_id
        )

        if not latest_deck:
            print("No pitch deck found for this startup.")
            return

        preferences = get_investor_preferences(connection)

        if not preferences:
            print("No investor preferences found.")
            return

        collection = connect_chromadb()

        evidence = retrieve_pitch_evidence(
            collection,
            startup_id,
            latest_deck["deck_id"]
        )

        rankings = rank_investors(
            startup,
            preferences,
            collection,
            latest_deck["deck_id"]
        )

        print("\n========== STARTUP DETAILS ==========")
        print(f"Startup: {startup['startup_name']}")
        print(f"Industry: {startup['industry_name']}")
        print(f"Stage: {startup['stage']}")
        print(f"Location: {startup['location']}")
        print(f"Latest Deck ID: {latest_deck['deck_id']}")

        print("\n========== PITCH DECK ANALYSIS ==========")

        for section, items in evidence.items():
            print(f"\n{section}")

            if not items:
                print("No evidence found.")
                continue

            for item in items:
                print(f"Chunk: {item['chunk_number']}")
                print(f"Distance: {item['distance']:.4f}")
                print(f"Evidence: {item['content'][:600]}")

        print("\n========== RANKED INVESTOR MATCHES ==========")

        for position, investor in enumerate(
            rankings,
            start=1
        ):
            print(f"\nRank {position}: {investor['investor_name']}")
            print(f"Organization: {investor['organization']}")
            print(
                f"Compatibility Score: "
                f"{investor['match_score']:.2f}%"
            )
            print(f"Data Coverage: {investor['coverage']}%")

            for dimension, score in investor["scores"].items():

                if score is None:
                    print(f"{dimension.title()}: Not available")
                else:
                    print(f"{dimension.title()}: {score}/100")

            for explanation in investor["explanations"]:
                print(f"- {explanation}")

        if save:
            inserted, updated = save_results(
                connection,
                startup_id,
                rankings
            )

            print(f"\nNew matches inserted: {inserted}")
            print(f"Existing matches updated: {updated}")

        else:
            print(
                "\nTest mode: MySQL records were not modified."
            )

    except Exception as error:
        print(f"Error: {error}")

    finally:
        if connection and connection.is_connected():
            connection.close()


if __name__ == "__main__":

    startup_id = (
        int(sys.argv[1])
        if len(sys.argv) > 1 and sys.argv[1].isdigit()
        else 6
    )

    save_mode = "--save" in sys.argv

    run_matching(
        startup_id,
        save=save_mode
    )
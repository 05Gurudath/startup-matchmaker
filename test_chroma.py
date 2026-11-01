
import chromadb

client = chromadb.PersistentClient(path="./chroma_db")

print("ChromaDB database connected successfully!")

collection = client.get_or_create_collection(
    name="startup_pitch_decks",
    metadata={"description": "Startup pitch deck information"}
)

print("Collection created successfully!")

startup_ids = [
    "startup_1",
    "startup_2",
    "startup_3"
]

startup_documents = [
    "An AI healthcare startup that uses machine learning for disease detection.",
    "A fintech startup providing digital payment and banking solutions.",
    "An agriculture startup using AI to improve crop production."
]

startup_metadata = [
    {"industry": "Healthcare", "startup_name": "MediAI"},
    {"industry": "Fintech", "startup_name": "PayFlow"},
    {"industry": "Agriculture", "startup_name": "AgriSmart"}
]

collection.upsert(
    ids=startup_ids,
    documents=startup_documents,
    metadatas=startup_metadata
)

print("Startup records inserted or updated successfully!")

print("\nTotal records stored:", collection.count())

search_query = "Startups working on medical technology and disease detection"

print("\nInvestor Search Query:")
print(search_query)

results = collection.query(
    query_texts=[search_query],
    n_results=2,
    include=["documents", "metadatas", "distances"]
)

print("\n========== SEMANTIC SEARCH RESULTS ==========")

for i, document in enumerate(results["documents"][0]):
    metadata = results["metadatas"][0][i]
    distance = results["distances"][0][i]

    print(f"\nResult {i + 1}")
    print("Startup Name:", metadata["startup_name"])
    print("Industry:", metadata["industry"])
    print("Description:", document)
    print("Distance:", round(distance, 4))

print("\n========== SEARCH COMPLETED ==========")

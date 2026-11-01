
from backend.database import get_db_connection

try:
    connection = get_db_connection()

    if connection.is_connected():
        print("MySQL connection successful!")
        print("Connected database:", connection.database)

    connection.close()

except Exception as error:
    print("Database connection failed:", error)


from getpass import getpass

from pwdlib import PasswordHash

from backend.database import get_db_connection

password_hash = PasswordHash.recommended()


def main():
    email = input("Enter user email: ").strip().lower()

    password = getpass("Enter new password: ")
    confirm_password = getpass("Confirm new password: ")

    if len(password) < 8:
        print("Password must contain at least 8 characters.")
        return

    if password != confirm_password:
        print("Passwords do not match.")
        return

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "SELECT user_id, name, role FROM users WHERE email = %s",
            (email,)
        )

        user = cursor.fetchone()

        if not user:
            print("User not found.")
            return

        hashed_password = password_hash.hash(password)

        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE user_id = %s",
            (hashed_password, user[0])
        )

        connection.commit()

        print("\nPassword updated successfully!")
        print("Name:", user[1])
        print("Role:", user[2])
        print("Password stored securely using Argon2.")

    except Exception as error:
        connection.rollback()
        print("Error updating password:", error)

    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()

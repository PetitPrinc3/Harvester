from telegram_parser import TelegramParser

if __name__ == "__main__":
    print("--- Harvester Telegram Setup ---")
    print("This script will log you into your Telegram account to create a session file.")
    print("This is a one-time process.")
    print("\nPlease enter your phone number, the code you receive, and your 2FA password if you have one.")
    print("-"*50)
    
    try:
        parser = TelegramParser()
        # This will trigger the interactive login if the session file doesn't exist.
        parser.setup_session()
        print("\n" + "-"*50)
        print("SUCCESS: The 'telegram_session.session' file has been created.")
        print("You can now start the main application container.")
    except Exception as e:
        print(f"\nAn error occurred during setup: {e}")

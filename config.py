import os
from dotenv import load_dotenv

load_dotenv()

TOKEN: str = os.getenv("DISCORD_TOKEN", "")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN が .env に設定されていません")

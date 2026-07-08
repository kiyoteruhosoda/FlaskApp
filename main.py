"""開発用エントリポイント。

本番では ``uvicorn asgi:app`` を使用すること。

開発時の起動方法::

    python main.py

または::

    uvicorn asgi:app --host 0.0.0.0 --port 5000 --reload
"""
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == '__main__':
    uvicorn.run(
        "asgi:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
    )

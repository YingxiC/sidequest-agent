from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from api.events import router as events_router

app = FastAPI(title="Day as Someone")
app.include_router(events_router)


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "frontend" / "sidequest.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
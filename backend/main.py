from fastapi import FastAPI

app = FastAPI(
    title="Recall API",
    version="0.1.0",
    description="Recall backend API skeleton"
)

@app.get("/")
async def root():
    return {"message": "Recall API is running"}

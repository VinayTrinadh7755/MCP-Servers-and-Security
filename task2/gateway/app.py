from fastapi import FastAPI


app = FastAPI(title="Task 2 MCP Security Gateway")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "gateway"}

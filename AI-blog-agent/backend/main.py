import os
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List

from .sitemap_parser import fetch_sitemap_urls
from .agent import BlogGenerationPipeline, AUTHOR_PERSONAS

app = FastAPI(title="AI Blog Writer Agent", description="SEO Blog writer for go4database.com")

# Define request schemas
class GenerateRequest(BaseModel):
    topic: str
    primary_keyword: str
    author: str  # samantha_bansil, chad_white, kath_pay, jordie_van_rijn, val_geisler
    target_word_count: Optional[int] = 2000
    custom_guidelines: Optional[str] = ""
    intent: Optional[str] = "Informational"
    faq_count: Optional[int] = 4
    case_study_required: Optional[str] = "No"
    expert_opinion_required: Optional[str] = "No"

# Serve the static files
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "static"))
os.makedirs(static_dir, exist_ok=True)

@app.get("/api/sitemap")
def get_sitemap():
    """
    Returns the parsed sitemap URLs from go4database.com
    """
    try:
        urls = fetch_sitemap_urls()
        return {"urls": urls, "count": len(urls)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/authors")
def get_authors():
    """
    Returns the list of available author personas with details
    """
    return AUTHOR_PERSONAS
   
@app.post("/api/generate")
def generate_blog(payload: GenerateRequest):
    """
    Triggers the blog generation pipeline
    """
    try:
        pipeline = BlogGenerationPipeline()
        
        # Simple local progress reporter (logs to console)
        def progress_log(percentage, message):
            print(f"[{percentage}%] {message}")
            
        result = pipeline.generate_blog(
            topic=payload.topic,
            primary_keyword=payload.primary_keyword,
            author_key=payload.author,
            target_word_count=payload.target_word_count,
            custom_guidelines=payload.custom_guidelines,
            progress_callback=progress_log,
            intent=payload.intent,
            faq_count=payload.faq_count,
            case_study_required=payload.case_study_required,
            expert_opinion_required=payload.expert_opinion_required
        )
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Mount static files at /
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(static_dir, "index.html"))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)

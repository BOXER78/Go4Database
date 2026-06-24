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

@app.get("/blog-api/sitemap")
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

@app.get("/blog-api/authors")
@app.get("/api/authors")
def get_authors():
    """
    Returns the list of available author personas with details
    """
    return AUTHOR_PERSONAS
   
@app.post("/blog-api/generate")
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

@app.get("/blog-api/debug/logs")
@app.get("/api/debug/logs-blog")
def get_debug_logs_blog(secret: Optional[str] = None):
    if secret != "debug123":
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_path = os.path.join(base_dir, "backend.log")
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                return {"status": "success", "logs": content[-20000:]}
        return {"status": "error", "message": f"Log file not found at {log_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(static_dir, "index.html"))

@app.get("/style.css")
def serve_style():
    return FileResponse(os.path.join(static_dir, "style.css"))

@app.get("/app.js")
def serve_js():
    return FileResponse(os.path.join(static_dir, "app.js"))

@app.get("/generated_blog.docx")
def serve_docx():
    return FileResponse(os.path.join(static_dir, "generated_blog.docx"))

@app.get("/generated_blog.html")
def serve_html():
    return FileResponse(os.path.join(static_dir, "generated_blog.html"))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    uvicorn.run("backend.main:app", host=host, port=port, reload=True)

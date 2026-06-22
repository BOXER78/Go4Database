import os
import sys
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.agent import BlogGenerationPipeline
from backend.sitemap_parser import fetch_sitemap_urls, get_contextual_internal_links

def main():
    print("--- Loading Environment Config ---")
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in .env")
        sys.exit(1)
    print("Gemini API Key: Found")

    print("\n--- Testing Sitemap Parser ---")
    sitemap_urls = fetch_sitemap_urls()
    print(f"Parsed {len(sitemap_urls)} URLs from Sitemap.")
    
    topic = "Email Marketing Campaign Benchmarks for Hospitality Industry"
    keyword = "email marketing benchmarks"
    
    internal_links = get_contextual_internal_links(topic, sitemap_urls, max_links=5)
    print(f"Topic: '{topic}'")
    print(f"Keyword: '{keyword}'")
    print("Selected Contextual Internal Links:")
    for link in internal_links:
        print(f" - {link}")

    print("\n--- Running Generation Pipeline (Simulated Call) ---")
    pipeline = BlogGenerationPipeline()
    
    def on_progress(percent, msg):
        print(f"[{percent}%] {msg}")
        
    try:
        result = pipeline.generate_blog(
            topic=topic,
            primary_keyword=keyword,
            author_key="samantha_bansil",
            target_word_count=800, # keeps it fast for testing
            custom_guidelines="Make sure to refer to the restaurant industry specifically.",
            progress_callback=on_progress,
            intent="Commercial",
            faq_count=5,
            case_study_required="Yes",
            expert_opinion_required="Yes"
        )
        
        print("\n--- Generation Success! ---")
        print(f"Title: {result['metadata']['title_tag']}")
        print(f"Slug: {result['metadata']['url_slug']}")
        print(f"Meta Description: {result['metadata']['meta_description']}")
        
        with open("backend/generated_blog.html", "w") as f:
            f.write(result["html"])
        print("[*] Saved HTML to backend/generated_blog.html")
        
        report = result['report']
        print(f"\n--- SEO Compliance Audit Score: {report['score_percentage']}% ---")
        print(f"Passed Checks: {report['passed_count']} of {report['total_checks']}")
        
        print("\nCheck details:")
        for name, check in report['checks'].items():
            status = "PASS" if check[0] else "FAIL"
            print(f" - [{status}] {name}: {check[1]}")
            
    except Exception as e:
        print(f"Pipeline failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

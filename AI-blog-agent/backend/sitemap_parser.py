import requests
import xml.etree.ElementTree as ET
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def fetch_sitemap_urls(sitemap_url="https://www.go4database.com/sitemap.xml"):
    """
    Fetches the sitemap and extracts all URLs.
    Falls back to parsing via BeautifulSoup if ElementTree fails due to namespace issues.
    """
    try:
        response = requests.get(sitemap_url, timeout=10)
        response.raise_for_status()
        
        urls = []
        # Try ElementTree parsing
        try:
            root = ET.fromstring(response.content)
            # Handle XML namespace
            namespace = ""
            if root.tag.startswith("{"):
                namespace = root.tag.split("}")[0] + "}"
                
            for url_node in root.findall(f"{namespace}url"):
                loc_node = url_node.find(f"{namespace}loc")
                if loc_node is not None and loc_node.text:
                    urls.append(loc_node.text.strip())
        except Exception as xml_err:
            logger.warning(f"XML parse failed: {xml_err}. Falling back to BeautifulSoup.")
            # Fallback to BeautifulSoup
            soup = BeautifulSoup(response.content, "xml")
            loc_tags = soup.find_all("loc")
            urls = [loc.text.strip() for loc in loc_tags if loc.text]
            
        # Clean URLs list: filter out non-HTTP(S) or empty URLs
        valid_urls = [u for u in urls if u.startswith("http")]
        
        # Default fallback URLs if sitemap is empty or failed to download
        if not valid_urls:
            valid_urls = [
                "https://www.go4database.com/",
                "https://www.go4database.com/pricing",
                "https://www.go4database.com/our-testimonial",
                "https://www.go4database.com/b2b",
                "https://www.go4database.com/b2b/restaurant-industry-list",
                "https://www.go4database.com/b2b/automotive-industry-email-list",
                "https://www.go4database.com/b2b/real-estate-industry-list",
                "https://www.go4database.com/b2b/oil-gas-industry-email-list",
                "https://www.go4database.com/b2b/aviation-industry-email-list",
                "https://www.go4database.com/b2b/travel-industry-email-list",
                "https://www.go4database.com/b2b/retail-industry-email-list"
            ]
        return list(set(valid_urls))
    except Exception as e:
        logger.error(f"Error fetching sitemap: {e}")
        # Static fallback list if network call fails completely
        return [
            "https://www.go4database.com/",
            "https://www.go4database.com/pricing",
            "https://www.go4database.com/our-testimonial",
            "https://www.go4database.com/b2b",
            "https://www.go4database.com/b2b/restaurant-industry-list",
            "https://www.go4database.com/b2b/automotive-industry-email-list",
            "https://www.go4database.com/b2b/real-estate-industry-list",
            "https://www.go4database.com/b2b/oil-gas-industry-email-list",
            "https://www.go4database.com/b2b/aviation-industry-email-list",
            "https://www.go4database.com/b2b/travel-industry-email-list",
            "https://www.go4database.com/b2b/retail-industry-email-list"
        ]

def get_contextual_internal_links(topic, sitemap_urls, max_links=10):
    """
    Selects context-relevant internal links from the list of sitemap URLs based on simple text matching/keywords.
    Categorizes the links and matches anchors.
    """
    selected_links = []
    # Identify link categories/anchors dynamically
    keywords_mapping = {
        "pricing": ["pricing", "cost", "rates", "subscription", "plans"],
        "testimonial": ["reviews", "testimonials", "customers", "clients", "success stories"],
        "b2b": ["b2b database", "business lists", "leads", "contact database"],
        "restaurant": ["restaurant", "food", "dining", "cafe"],
        "automotive": ["automotive", "car", "dealer", "auto"],
        "real-estate": ["real estate", "property", "realtor", "brokers"],
        "oil-gas": ["oil", "gas", "energy", "petroleum"],
        "aviation": ["aviation", "airline", "aircraft", "aerospace"],
        "travel": ["travel", "tourism", "agency", "hospitality"],
        "retail": ["retail", "ecommerce", "shops", "merchant"]
    }
    
    # Check simple matches between the topic keywords and sitemap URLs
    topic_lower = topic.lower()
    
    # Sort sitemap urls: prioritize ones containing industry keywords
    scored_urls = []
    for url in sitemap_urls:
        score = 0
        url_lower = url.lower()
        
        # Avoid linking to the homepage too much, prioritize specific pages
        if url_lower.endswith(".com") or url_lower.endswith(".com/"):
            score = 1
        else:
            score = 2
            
        # Match topic relevance
        for category, kws in keywords_mapping.items():
            if category in url_lower:
                for kw in kws:
                    if kw in topic_lower:
                        score += 5
                        break
        scored_urls.append((url, score))
        
    # Sort descending by score
    scored_urls.sort(key=lambda x: x[1], reverse=True)
    
    # Pick the top unique URLs
    for url, score in scored_urls:
        if len(selected_links) >= max_links:
            break
        selected_links.append(url)
        
    return selected_links

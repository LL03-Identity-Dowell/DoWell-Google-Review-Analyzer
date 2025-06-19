import eventlet
eventlet.monkey_patch()

from flask import Flask, request, jsonify, send_file
from flask_socketio import SocketIO, emit, join_room
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time, csv, uuid, datetime, re
from io import StringIO
import eventlet
import re
import os
import hashlib
import random


app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   logger=True,
                   engineio_logger=True,
                   async_mode='eventlet')
SESSIONS = {}
ACTIVE_JOBS = {}


# def init_driver():
#     chrome_options = Options()
#     chrome_options.add_argument('--headless')
#     chrome_options.add_argument('--no-sandbox')
#     chrome_options.add_argument('--disable-dev-shm-usage')
#     chrome_options.add_argument('--disable-blink-features=AutomationControlled')
#     chrome_options.add_argument('--window-size=1920,1080')
#     chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36')

#     # Install with ChromeDriverManager and correct the path
#     raw_path = ChromeDriverManager().install()
#     dir_path = os.path.dirname(raw_path)

#     # Find the actual executable in the directory
#     driver_path = None
#     for fname in os.listdir(dir_path):
#         full_path = os.path.join(dir_path, fname)
#         if "chromedriver" in fname and os.access(full_path, os.X_OK) and not fname.endswith(".chromedriver"):
#             driver_path = full_path
#             break

#     if not driver_path:
#         raise Exception("Failed to find a valid chromedriver executable.")

#     service = Service(driver_path)
#     driver = webdriver.Chrome(service=service, options=chrome_options)

#     # Hide webdriver flag
#     driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
#         "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
#     })

#     return driver

def init_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36')

    # Try to use local chromedriver if it exists
    local_driver_path = os.path.join(os.getcwd(), 'chromedriver')
    if os.path.exists(local_driver_path) and os.access(local_driver_path, os.X_OK):
        driver_path = local_driver_path
    else:
        # Use webdriver-manager to download (requires internet)
        raw_path = ChromeDriverManager().install()
        dir_path = os.path.dirname(raw_path)

        # Find the actual executable
        driver_path = None
        for fname in os.listdir(dir_path):
            full_path = os.path.join(dir_path, fname)
            if "chromedriver" in fname and os.access(full_path, os.X_OK) and not fname.endswith(".chromedriver"):
                driver_path = full_path
                break

        if not driver_path:
            raise Exception("Failed to find a valid chromedriver executable.")

    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Hide webdriver flag
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })

    return driver

@app.route('/api/scrape', methods=['POST'])
def start_scraping():
    data = request.get_json()
    url = data.get('url')
    days = data.get('days')
    custom_date = data.get('customDate')
    email = data.get('email')
    session_id = data.get('sessionId')

    if not session_id:
        return jsonify({'error': 'Missing sessionId'}), 400

    ACTIVE_JOBS[session_id] = True
    socketio.start_background_task(scrape_and_analyze, url, days, custom_date, email, session_id)
    return jsonify({'message': 'Scraping started'})

@socketio.on('join_session')
def on_join(data):
    session_id = data['sessionId']
    join_room(session_id)
    print(f"[🏠 JOIN] Client joined session: {session_id}")
    
    # Send immediate confirmation
    emit('session_joined', {'sessionId': session_id}, room=session_id)
    
    # If there are existing reviews, send them
    if session_id in SESSIONS:
        existing_reviews = SESSIONS[session_id]
        if existing_reviews:
            print(f"[📤 RESEND] Sending {len(existing_reviews)} existing reviews")
            emit('review', existing_reviews, room=session_id)

@socketio.on('connect')
def on_connect():
    print(f"[🔌 CONNECT] Client connected: {request.sid}")

@socketio.on('disconnect')
def on_disconnect():
    print(f"[🔌 DISCONNECT] Client disconnected: {request.sid}")

@socketio.on('cancel_scraping')
def cancel_job(data):
    session_id = data.get('sessionId')
    if session_id:
        ACTIVE_JOBS[session_id] = False
        emit('status_update', {'progress': 0, 'status': 'Scraping cancelled.'}, room=session_id)

def parse_relative_date(text):
    now = datetime.datetime.now()
    text = text.lower().strip()
    
    # Handle absolute dates first
    try:
        # Try parsing "Month Year" format (e.g., "January 2024")
        return datetime.datetime.strptime(text, "%B %Y")
    except:
        pass
    
    try:
        # Try parsing "Day Month Year" format (e.g., "15 January 2024")
        return datetime.datetime.strptime(text, "%d %B %Y")
    except:
        pass
    
    try:
        # Try parsing "Month Day, Year" format (e.g., "January 15, 2024")
        return datetime.datetime.strptime(text, "%B %d, %Y")
    except:
        pass
    
    # Handle relative dates
    if 'today' in text or 'just now' in text:
        return now
    if 'yesterday' in text or 'a day ago' in text or '1 day ago' in text:
        return now - datetime.timedelta(days=1)
    if 'a week ago' in text or '1 week ago' in text:
        return now - datetime.timedelta(weeks=1)
    if '2 weeks ago' in text or 'Two weeks ago' in text or 'two weeks ago' in text:
        return now - datetime.timedelta(weeks=2)
    if 'a month ago' in text or '1 month ago' in text:
        return now - datetime.timedelta(days=30)
    if '3 months ago' in text or 'Three months ago' in text or 'three months ago' in text:
        return now - datetime.timedelta(days=90)
    if 'a year ago' in text or '1 year ago' in text:
        return now - datetime.timedelta(days=365)
    
    # Handle hours ago
    hour_match = re.search(r'(\d+)\s*hours?\s*ago', text)
    if hour_match:
        hours = int(hour_match.group(1))
        return now - datetime.timedelta(hours=hours)
    
    # Handle minutes ago
    minute_match = re.search(r'(\d+)\s*minutes?\s*ago', text)
    if minute_match:
        minutes = int(minute_match.group(1))
        return now - datetime.timedelta(minutes=minutes)
    
    # Handle numbered relative dates
    day_match = re.search(r'(\d+)\s*days?\s*ago', text)
    if day_match:
        days = int(day_match.group(1))
        return now - datetime.timedelta(days=days)
    
    week_match = re.search(r'(\d+)\s*weeks?\s*ago', text)
    if week_match:
        weeks = int(week_match.group(1))
        return now - datetime.timedelta(weeks=weeks)
    
    month_match = re.search(r'(\d+)\s*months?\s*ago', text)
    if month_match:
        months = int(month_match.group(1))
        return now - datetime.timedelta(days=30*months)
    
    year_match = re.search(r'(\d+)\s*years?\s*ago', text)
    if year_match:
        years = int(year_match.group(1))
        return now - datetime.timedelta(days=365*years)
    
    # If we can't parse it, return current time
    print(f"[⚠️ DATE] Could not parse date: '{text}', using current time")
    return now

def analyze_sentiment(reviews):
    """Simple sentiment analysis based on ratings and keywords"""
    if not reviews:
        return "No reviews to analyze"
    
    total_reviews = len(reviews)
    avg_rating = sum(r['rating'] for r in reviews) / total_reviews
    
    # Count positive/negative keywords
    positive_words = ['great', 'excellent', 'amazing', 'wonderful', 'fantastic', 'love', 'perfect', 'best', 'awesome', 'outstanding']
    negative_words = ['terrible', 'awful', 'horrible', 'worst', 'hate', 'disgusting', 'poor', 'bad', 'disappointing', 'rude']
    
    positive_count = 0
    negative_count = 0
    
    for review in reviews:
        text = review['text'].lower()
        positive_count += sum(1 for word in positive_words if word in text)
        negative_count += sum(1 for word in negative_words if word in text)
    
    sentiment = "Neutral"
    if avg_rating >= 4.0:
        sentiment = "Very Positive"
    elif avg_rating >= 3.5:
        sentiment = "Positive"
    elif avg_rating >= 2.5:
        sentiment = "Mixed"
    elif avg_rating >= 2.0:
        sentiment = "Negative"
    else:
        sentiment = "Very Negative"
    
    return f"{sentiment} - Average rating: {avg_rating:.1f}/5.0 stars. Analyzed from {total_reviews} reviews with {positive_count} positive mentions and {negative_count} negative mentions."

def generate_swot_analysis(reviews):
    """Generate SWOT analysis based on review content"""
    if not reviews:
        return {'strengths': [], 'weaknesses': [], 'opportunities': [], 'threats': []}
    
    # Keywords mapping for SWOT
    strength_keywords = ['excellent', 'great', 'amazing', 'professional', 'friendly', 'clean', 'quality', 'fast', 'convenient']
    weakness_keywords = ['slow', 'expensive', 'rude', 'dirty', 'poor', 'bad', 'disappointing', 'unprofessional']
    opportunity_keywords = ['recommend', 'potential', 'expand', 'improve', 'better', 'more']
    threat_keywords = ['competition', 'expensive', 'alternative', 'switching', 'leaving']
    
    strengths = []
    weaknesses = []
    opportunities = []
    threats = []
    
    # Analyze high-rated reviews for strengths
    high_rated = [r for r in reviews if r['rating'] >= 4]
    for review in high_rated:
        text = review['text'].lower()
        for keyword in strength_keywords:
            if keyword in text and len(strengths) < 5:
                strengths.append(f"Customers appreciate {keyword} service/experience")
                break
    
    # Analyze low-rated reviews for weaknesses
    low_rated = [r for r in reviews if r['rating'] <= 2]
    for review in low_rated:
        text = review['text'].lower()
        for keyword in weakness_keywords:
            if keyword in text and len(weaknesses) < 5:
                weaknesses.append(f"Issues with {keyword} service/experience mentioned")
                break
    
    # Generate general insights
    avg_rating = sum(r['rating'] for r in reviews) / len(reviews)
    if avg_rating >= 4.0:
        strengths.append("High average customer satisfaction rating")
    
    if len(high_rated) > len(low_rated) * 2:
        strengths.append("Strong positive review ratio")
    
    if len(low_rated) > len(reviews) * 0.3:
        weaknesses.append("Significant number of negative reviews")
    
    opportunities.append("Opportunity to address negative feedback")
    opportunities.append("Potential to leverage positive reviews for marketing")
    
    if len(low_rated) > 0:
        threats.append("Risk of reputation damage from negative reviews")
    
    return {
        'strengths': strengths[:5],
        'weaknesses': weaknesses[:5], 
        'opportunities': opportunities[:5],
        'threats': threats[:5]
    }

def scrape_and_analyze(url, days, custom_date, email, session_id):
    driver = init_driver()

    try:
        socketio.emit('status_update', {'progress': 5, 'status': 'Loading Google Maps page...'}, room=session_id)
        driver.get(url)
        time.sleep(3)

        if custom_date:
            cutoff_date = datetime.datetime.strptime(custom_date, "%Y-%m-%d")
        else:
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=int(days))

        socketio.emit('status_update', {'progress': 10, 'status': 'Finding Reviews tab...'}, room=session_id)

        # Click Reviews tab - try multiple selectors
        try:
            review_selectors = [
                "//button[contains(., 'Reviews') or contains(., 'review')]",
                "//div[contains(., 'Reviews') or contains(., 'review')]//parent::button",
                "//span[contains(., 'Reviews')]//ancestor::button",
                "//*[contains(@data-value, 'Reviews')]",
                "//button[@data-tab-index='1']"
            ]
            
            review_button = None
            for selector in review_selectors:
                try:
                    elements = driver.find_elements(By.XPATH, selector)
                    if elements:
                        review_button = elements[0]
                        break
                except:
                    continue

            if review_button:
                driver.execute_script("arguments[0].click();", review_button)
                print("[🖱️ CLICK] Reviews tab clicked.")
                time.sleep(4)
            else:
                raise Exception("Reviews tab not found")

        except Exception as e:
            socketio.emit('status_update', {'progress': 0, 'status': 'Could not find Reviews tab', 'error': True}, room=session_id)
            driver.quit()
            return

        socketio.emit('status_update', {'progress': 20, 'status': 'Setting up sort by newest...'}, room=session_id)

        # Scroll to ensure elements are loaded
        driver.execute_script("window.scrollBy(0, 1000);")
        time.sleep(2)

        # Click Sort button and select Newest
        try:
            sort_selectors = [
                "//button[.//span[contains(text(), 'Sort')]]",
                "//button[contains(text(), 'Sort')]",
                "//div[contains(text(), 'Sort')]//parent::button",
                "//*[contains(text(), 'Sort')]",
                "//button[@data-value='Sort']"
            ]
            
            sort_button = None
            for selector in sort_selectors:
                try:
                    sort_button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, selector)))
                    break
                except:
                    continue

            if sort_button:
                driver.execute_script("arguments[0].click();", sort_button)
                print("[🖱️ CLICK] Sort button clicked.")
                time.sleep(2)

                # Select Newest option
                newest_selectors = [
                    "//li[contains(text(), 'Newest')]",
                    "//span[contains(text(), 'Newest')]",
                    "//div[contains(text(), 'Newest')]",
                    "//*[contains(text(), 'Recent')]",
                    "//div[@role='menuitem'][contains(., 'Newest')]"
                ]
                
                for selector in newest_selectors:
                    try:
                        newest_option = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, selector)))
                        driver.execute_script("arguments[0].click();", newest_option)
                        print("[↕️ SORT] Clicked on 'Newest'")
                        time.sleep(3)
                        break
                    except:
                        continue
        except Exception as e:
            print("[⚠️ WARN] Could not set sort order:", str(e))

        socketio.emit('status_update', {'progress': 30, 'status': 'Scrolling to load reviews...'}, room=session_id)

        # Find scrollable container - try multiple selectors
        scrollable = None
        scrollable_selectors = [
            'div.m6QErb.XiKgde',
            'div[role="main"]',
            'div.section-scrollbox',
            'div.section-layout'
        ]
        
        for selector in scrollable_selectors:
            try:
                scrollable = driver.find_element(By.CSS_SELECTOR, selector)
                break
            except:
                continue
        
        if not scrollable:
            scrollable = driver.find_element(By.TAG_NAME, "body")

        processed_review_ids = set()
        reviews = []
        scroll_count = 0
        stale_scrolls = 0
        max_stale_scrolls = 15  # Reduced from 20
        max_scrolls = 100  # Increased from 60

        print(f"[🎯 TARGET] Looking for reviews newer than {cutoff_date.date()}")

        while scroll_count < max_scrolls and stale_scrolls < max_stale_scrolls:
            if not ACTIVE_JOBS.get(session_id, True):
                driver.quit()
                return

            # Try multiple review selectors
            review_selectors = [
                'div[data-review-id]',
                'div[jsaction*="review"]',
                'div.jftiEf',
                'div.MyEned',
                'div[data-review-id] > div'
            ]
            
            # review_blocks = []
            # for selector in review_selectors:
            #     try:
            #         blocks = driver.find_elements(By.CSS_SELECTOR, selector)
            #         if blocks:
            #             review_blocks = blocks
            #             break
            #     except:
            #         continue

            # if not review_blocks:
            #     print("[⚠️ WARN] No review blocks found, trying alternative method")
            #     # Alternative method: look for common review patterns
            #     review_blocks = driver.find_elements(By.XPATH, "//div[contains(@class, 'jftiEf') or contains(@jsaction, 'review')]")

            review_blocks = []
            
            # Method 1: Look for divs with review-related attributes
            try:
                review_blocks = driver.find_elements(By.CSS_SELECTOR, 'div[data-review-id]')
                print(f"[🔍 METHOD1] Found {len(review_blocks)} reviews with data-review-id")
            except:
                pass
            
            # Method 2: If method 1 fails, try broader selectors
            if not review_blocks:
                try:
                    review_blocks = driver.find_elements(By.CSS_SELECTOR, 'div.jftiEf')
                    print(f"[🔍 METHOD2] Found {len(review_blocks)} reviews with jftiEf class")
                except:
                    pass
            
            # Method 3: Even broader approach
            if not review_blocks:
                try:
                    # Look for elements that contain both author and rating
                    review_blocks = driver.find_elements(By.XPATH, "//div[.//span[@class='d4r55'] and .//span[contains(@class,'kvMYJc')]]")
                    print(f"[🔍 METHOD3] Found {len(review_blocks)} reviews with XPath")
                except:
                    pass
            
            # Method 4: Last resort - look for any div containing review-like content
            if not review_blocks:
                try:
                    review_blocks = driver.find_elements(By.XPATH, "//div[.//span[@class='rsqaWe']]")
                    print(f"[🔍 METHOD4] Found {len(review_blocks)} reviews with date elements")
                except:
                    pass

            if not review_blocks:
                print("[❌ ERROR] No review blocks found with any method")
                stale_scrolls += 1
                continue

            print(f"[🔄 SCROLL {scroll_count + 1}] Found {len(review_blocks)} review blocks")

            new_reviews_found = False
            reviews_processed_this_scroll = 0

            for block in review_blocks:
                try:
                    # Get or generate review ID
                    review_id = block.get_attribute('data-review-id')
                    if not review_id:
                        # Try to extract text-based content for ID
                        try:
                            # Get the first 50 characters of the review text for uniqueness
                            temp_text = ""
                            try:
                                temp_text_elem = block.find_element(By.CSS_SELECTOR, ".MyEned, .wiI7pd")
                                temp_text = temp_text_elem.text[:50]
                            except:
                                pass
                            
                            # Get author and date for ID
                            temp_author = ""
                            temp_date = ""
                            try:
                                temp_author_elem = block.find_element(By.CSS_SELECTOR, ".d4r55")
                                temp_author = temp_author_elem.text
                            except:
                                pass
                            try:
                                temp_date_elem = block.find_element(By.CSS_SELECTOR, '.rsqaWe')
                                temp_date = temp_date_elem.text
                            except:
                                pass
                            
                            # Create unique ID from available data
                            review_id = f"{temp_author}_{temp_date}_{temp_text}".replace(" ", "_").replace("\n", "")[:100]
                            
                            if not review_id or review_id == "__":
                                # Last resort: use element location
                                location = block.location
                                review_id = f"review_{location['x']}_{location['y']}"
                                
                        except Exception as e:
                            print(f"[⚠️ ID] Could not generate review ID: {e}")
                            continue
                    
                    if review_id in processed_review_ids:
                        continue

                    # Extract date with multiple selectors
                    date_text = ""
                    date_selectors = ['.rsqaWe', '.DU9Pgb', 'span[class*="rsqaWe"]']
                    for date_selector in date_selectors:
                        try:
                            date_element = block.find_element(By.CSS_SELECTOR, date_selector)
                            date_text = date_element.text.strip()
                            break
                        except:
                            continue
                    
                    if not date_text:
                        print("[⚠️ WARN] Could not extract date, skipping review")
                        continue
                    
                    parsed_date = parse_relative_date(date_text)
                    if parsed_date < cutoff_date:
                        continue

                    # Extract author with multiple selectors
                    author = ""
                    author_selectors = [".d4r55", ".YBMEb", "div[data-href*='contrib']"]
                    for author_selector in author_selectors:
                        try:
                            author_element = block.find_element(By.CSS_SELECTOR, author_selector)
                            author = author_element.text.strip()
                            break
                        except:
                            continue
                    
                    if not author:
                        author = "Anonymous"

                    # Extract rating with multiple approaches
                    rating = 0
                    try:
                        # Method 1: aria-label approach
                        rating_element = block.find_element(By.CSS_SELECTOR, "span[class*='kvMYJc']")
                        aria_label = rating_element.get_attribute("aria-label")
                        rating_match = re.search(r'(\d+(?:\.\d+)?)', aria_label)
                        if rating_match:
                            rating = float(rating_match.group(1))
                    except:
                        try:
                            # Method 2: count filled stars
                            stars = block.find_elements(By.CSS_SELECTOR, "span[style*='width']")
                            if stars:
                                style = stars[0].get_attribute("style")
                                width_match = re.search(r'width:\s*(\d+)%', style)
                                if width_match:
                                    rating = float(width_match.group(1)) / 20  # 100% = 5 stars
                        except:
                            # Method 3: look for star elements
                            try:
                                star_elements = block.find_elements(By.CSS_SELECTOR, ".kvMYJc")
                                rating = len(star_elements)
                            except:
                                pass

                    # Extract review text with multiple selectors
                    text = ""
                    text_selectors = [".MyEned", ".wiI7pd", "span[jsaction*='expand']", ".review-text"]
                    for text_selector in text_selectors:
                        try:
                            text_element = block.find_element(By.CSS_SELECTOR, text_selector)
                            text = text_element.text.strip()
                            break
                        except:
                            continue

                    # Extract photo if available
                    photo = None
                    try:
                        photo_elements = block.find_elements(By.CSS_SELECTOR, 'img.tz3DLd, img[src*="googleusercontent"]')
                        if photo_elements:
                            photo = photo_elements[0].get_attribute("src")
                    except:
                        pass

                    review = {
                        "author": author,
                        "rating": rating,
                        "date": parsed_date.strftime("%Y-%m-%d"),
                        "text": text,
                        "photo": photo
                    }

                    reviews.append(review)
                    processed_review_ids.add(review_id)
                    new_reviews_found = True
                    reviews_processed_this_scroll += 1

                    if session_id not in SESSIONS:
                        SESSIONS[session_id] = []
                    SESSIONS[session_id].append(review)

                    # Emit individual review to frontend
                    print(f"[🔄 EMIT] Emitting review to session {session_id}: {review['author']}")
                    socketio.emit('review', [review], to=session_id)
                    print(f"[✅ NEW] Processed review from {author} ({parsed_date.date()}) - Rating: {rating}")

                    time.sleep(0.1)

                except Exception as e:
                    print(f"[⚠️ EXTRACT] Error extracting review: {e}")
                    continue

            print(f"[📊 STATS] Scroll {scroll_count + 1}: Processed {reviews_processed_this_scroll} new reviews, Total: {len(reviews)}")

            # Update progress and status
            progress = min(90, 30 + (scroll_count * 60 / max_scrolls))
            socketio.emit('status_update', {
                'progress': progress, 
                'status': f'Found {len(reviews)} reviews... (scroll {scroll_count + 1}, found {reviews_processed_this_scroll} this round)'
            }, room=session_id)

            if new_reviews_found:
                stale_scrolls = 0
                print(f"[📈 PROGRESS] Total reviews: {len(reviews)}, This scroll: {reviews_processed_this_scroll}")
            else:
                stale_scrolls += 1
                print(f"[🌀 STALE] No new reviews. Stale count: {stale_scrolls}/{max_stale_scrolls}")

            if stale_scrolls >= max_stale_scrolls:
                print(f"[🛑 STOP] Stopping due to {max_stale_scrolls} consecutive scrolls without new reviews")
                break

            if reviews_processed_this_scroll > 0:
                stale_scrolls = 0
                new_reviews_found = True
                print(f"[✅ ACTIVE] Found {reviews_processed_this_scroll} new reviews this scroll")
            else:
                stale_scrolls += 1
                print(f"[🌀 STALE] No new reviews found. Stale count: {stale_scrolls}/{max_stale_scrolls}")

            # Check if we should continue
            if stale_scrolls >= max_stale_scrolls:
                print(f"[🛑 STOP] Stopping due to {max_stale_scrolls} consecutive scrolls without new reviews")
                break

            try:
                scrollable = driver.find_element(By.CSS_SELECTOR, "div.m6QErb.DxyBCb.kA9KIf.dS8AEf")
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scrollable)
                print(f"[↕️ SCROLL {scroll_count}] Scrolled review container to bottom")
            except Exception as e:
                print(f"[⚠️ SCROLL] Failed to scroll review container: {e}")

            # ⏱ Wait a bit to let reviews load
            time.sleep(random.uniform(2.5, 4.5))

            try:
                more_buttons = driver.find_elements(By.CSS_SELECTOR, 'button[jsaction="pane.review.expandReview"]')
                for btn in more_buttons:
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.2)
            except Exception as e:
                print(f"[⚠️ MORE] Could not expand reviews: {e}")

            scroll_count += 1

            # # More aggressive scrolling
            # scroll_distance = 3000  # Increased scroll distance
            # try:
            #     driver.execute_script(f"arguments[0].scrollTop += {scroll_distance}", scrollable)
            # except:
            #     pass
            
            # # Also try scrolling the main window
            # driver.execute_script(f"window.scrollBy(0, {scroll_distance})")

            # driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            
            # time.sleep(3)  # Reduced wait time
            # scroll_count += 1

            # Try clicking "More reviews" button if it exists
            # try:
            #     more_button = driver.find_element(By.XPATH, "//button[contains(., 'more') or contains(., 'More')]")
            #     if more_button.is_displayed():
            #         driver.execute_script("arguments[0].click();", more_button)
            #         time.sleep(2)
            #         print("[🔄 MORE] Clicked 'More reviews' button")
            # except:
            #     pass

        # Store reviews in session for CSV download
        SESSIONS[session_id] = reviews
        
        # Generate and emit sentiment analysis
        socketio.emit('status_update', {'progress': 92, 'status': 'Analyzing sentiment...'}, room=session_id)
        sentiment = analyze_sentiment(reviews)
        socketio.emit('sentiment_update', {'text': sentiment}, room=session_id)
        
        # Generate and emit SWOT analysis
        socketio.emit('status_update', {'progress': 95, 'status': 'Generating SWOT analysis...'}, room=session_id)
        swot = generate_swot_analysis(reviews)
        socketio.emit('swot_update', swot, room=session_id)

        driver.quit()

        if not reviews:
            socketio.emit('status_update', {'progress': 100, 'status': 'No reviews found in the specified date range'}, room=session_id)
            return

        socketio.emit('status_update', {
            'progress': 100, 
            'status': f'Analysis complete! Found {len(reviews)} reviews.'
        }, room=session_id)

        print(f"[🎉 COMPLETE] Scraping finished. Total reviews: {len(reviews)}")

    except Exception as e:
        print(f"[❌ ERROR] Scraping failed: {e}")
        import traceback
        traceback.print_exc()
        socketio.emit('status_update', {
            'progress': 0,
            'status': f'Scraping failed: {str(e)}',
            'error': True
        }, room=session_id)
        if driver:
            driver.quit()

@app.route('/api/download-csv/<session_id>', methods=['GET'])
def download_csv(session_id):
    reviews = SESSIONS.get(session_id, [])
    if not reviews:
        return jsonify({'error': 'No data'}), 404

    si = StringIO()
    writer = csv.DictWriter(si, fieldnames=['date', 'author', 'rating', 'text', 'photo'])
    writer.writeheader()
    writer.writerows(reviews)
    si.seek(0)

    return send_file(
        StringIO(si.read()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'reviews_{session_id}.csv'
    )

if __name__ == '__main__':
    # socketio.run(app, port=5000, debug=True)
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

import eventlet
eventlet.monkey_patch()

import datetime
import uuid
import csv
import time
import random
import hashlib
import os
import re
from io import StringIO
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium import webdriver
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room
from flask import Flask, request, jsonify, send_file
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
import textwrap

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app,
                    cors_allowed_origins="*",
                    logger=True,
                    engineio_logger=True,
                    async_mode='eventlet')
SESSIONS = {}
ACTIVE_JOBS = {}

def init_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument(
        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
    )

    # Use the chromedriver path set in Docker image
    driver_path = "/usr/local/bin/chromedriver"

    if not os.path.exists(driver_path) or not os.access(driver_path, os.X_OK):
        raise FileNotFoundError(f"ChromeDriver not found or not executable at: {driver_path}")

    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Stealth mode: hide navigator.webdriver flag
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })

    return driver

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Docker and load balancers"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.datetime.now().isoformat(),
        'service': 'google-review-analyzer',
        'version': '1.0.0'
    }), 200

# Add /api/health for compatibility
@app.route('/api/health', methods=['GET'])
def api_health_check():
    return health_check()

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
    socketio.start_background_task(
        scrape_and_analyze, url, days, custom_date, email, session_id)
    return jsonify({'message': 'Scraping started'})


@app.route('/api/scrape-bulk', methods=['POST'])
def start_bulk_scraping():
    data = request.get_json()
    urls = data.get('urls', [])
    days = data.get('days')
    custom_date = data.get('customDate')
    email = data.get('email')
    session_id = data.get('sessionId')

    if not session_id:
        return jsonify({'error': 'Missing sessionId'}), 400
    
    if not urls or len(urls) == 0:
        return jsonify({'error': 'No URLs provided'}), 400
    
    if len(urls) > 10000:
        return jsonify({'error': 'Maximum 10,000 URLs allowed'}), 400

    ACTIVE_JOBS[session_id] = True
    socketio.start_background_task(
        scrape_bulk_and_analyze, urls, days, custom_date, email, session_id)
    return jsonify({'message': 'Bulk scraping started'})


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
            print(
                f"[📤 RESEND] Sending {len(existing_reviews)} existing reviews")
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
        emit('status_update', {'progress': 0,
             'status': 'Scraping cancelled.'}, room=session_id)


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

    print(f"[⚠️ DATE] Could not parse date: '{text}', using current time")
    return now

def extract_business_details(driver):
    """Extract business details from Google Maps page"""
    business_details = {
        'name': '',
        'address': '',
        'phone': '',
        'website': '',
        'hours': '',
        'rating': '',
        'total_reviews': '',
        'category': '',
        'description': ''
    }
    
    try:
        # Business name
        name_selectors = [
            'h1[data-attrid="title"]',
            'h1.DUwDvf',
            'h1.fontHeadlineLarge',
            '[data-attrid="title"] h1',
            'h1'
        ]
        
        for selector in name_selectors:
            try:
                name_element = driver.find_element(By.CSS_SELECTOR, selector)
                business_details['name'] = name_element.text.strip()
                break
            except:
                continue
        
        # Address
        address_selectors = [
            '[data-item-id="address"] .Io6YTe',
            '[data-value="Address"] .Io6YTe',
            '[data-attrid="kc:/location/location:address"]',
            '.Io6YTe'
        ]
        
        for selector in address_selectors:
            try:
                address_element = driver.find_element(By.CSS_SELECTOR, selector)
                business_details['address'] = address_element.text.strip()
                break
            except:
                continue
        
        # Phone number
        phone_selectors = [
            '[data-item-id="phone"] .Io6YTe',
            '[data-value="Phone"] .Io6YTe',
            '[data-attrid="kc:/business/telephone"]',
            'span[data-dtype="d3ifr"]'
        ]
        
        for selector in phone_selectors:
            try:
                phone_element = driver.find_element(By.CSS_SELECTOR, selector)
                business_details['phone'] = phone_element.text.strip()
                break
            except:
                continue
        
        # Website
        website_selectors = [
            '[data-item-id="authority"] a',
            '[data-value="Website"] a',
            'a[data-value="Website"]'
        ]
        
        for selector in website_selectors:
            try:
                website_element = driver.find_element(By.CSS_SELECTOR, selector)
                business_details['website'] = website_element.get_attribute('href')
                break
            except:
                continue
        
        # Overall rating and total reviews
        try:
            rating_element = driver.find_element(By.CSS_SELECTOR, '.F7nice span[aria-hidden="true"]')
            business_details['rating'] = rating_element.text.strip()
        except:
            try:
                rating_element = driver.find_element(By.CSS_SELECTOR, '.ceNzKf')
                business_details['rating'] = rating_element.text.strip()
            except:
                pass
        
        try:
            reviews_element = driver.find_element(By.CSS_SELECTOR, '.F7nice .bC3Nkc')
            business_details['total_reviews'] = reviews_element.text.strip()
        except:
            try:
                reviews_element = driver.find_element(By.CSS_SELECTOR, '.HHrUdb')
                business_details['total_reviews'] = reviews_element.text.strip()
            except:
                pass
        
        # Category
        try:
            category_element = driver.find_element(By.CSS_SELECTOR, '.DkEaL')
            business_details['category'] = category_element.text.strip()
        except:
            pass
        
        # Hours
        try:
            hours_element = driver.find_element(By.CSS_SELECTOR, '[data-item-id="oh"] .Io6YTe')
            business_details['hours'] = hours_element.text.strip()
        except:
            pass
        
        print(f"[🏢 BUSINESS] Extracted details: {business_details}")
        
    except Exception as e:
        print(f"[⚠️ BUSINESS] Error extracting business details: {e}")
    
    return business_details

def generate_pdf_report(business_details, reviews, session_id):
    """Generate PDF report with business details and reviews"""
    filename = f"business_report_{session_id}.pdf"
    filepath = f"/tmp/{filename}"
    
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=20,
        spaceAfter=30,
        alignment=TA_CENTER,
        textColor=colors.HexColor('#2563eb')
    )
    
    section_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=16,
        spaceAfter=12,
        textColor=colors.HexColor('#1f2937')
    )
    
    # Title
    story.append(Paragraph("Business Analysis Report", title_style))
    story.append(Spacer(1, 20))
    
    # Business Details Section
    story.append(Paragraph("Business Information", section_style))
    
    business_data = [
        ['Business Name:', business_details.get('name', 'N/A')],
        ['Address:', business_details.get('address', 'N/A')],
        ['Phone:', business_details.get('phone', 'N/A')],
        ['Website:', business_details.get('website', 'N/A')],
        ['Category:', business_details.get('category', 'N/A')],
        ['Overall Rating:', business_details.get('rating', 'N/A')],
        ['Total Reviews:', business_details.get('total_reviews', 'N/A')],
        ['Hours:', business_details.get('hours', 'N/A')]
    ]
    
    business_table = Table(business_data, colWidths=[2*inch, 4*inch])
    business_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    story.append(business_table)
    story.append(Spacer(1, 30))
    
    # Reviews Section
    story.append(Paragraph(f"Customer Reviews ({len(reviews)} reviews)", section_style))
    story.append(Spacer(1, 10))
    
    for i, review in enumerate(reviews, 1):
        # Review header
        review_header = f"Review #{i} - {review['author']} - {review['rating']}⭐ - {review['date']}"
        story.append(Paragraph(review_header, styles['Heading3']))
        
        # Review text
        review_text = review.get('text', 'No text provided')
        wrapped_text = textwrap.fill(review_text, width=80)
        story.append(Paragraph(wrapped_text, styles['Normal']))
        story.append(Spacer(1, 15))
    
    doc.build(story)
    return filepath

def generate_txt_report(business_details, reviews, session_id):
    """Generate TXT report with business details and reviews"""
    filename = f"business_report_{session_id}.txt"
    filepath = f"/tmp/{filename}"
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("BUSINESS ANALYSIS REPORT\n")
        f.write("=" * 50 + "\n\n")
        
        # Business Details
        f.write("BUSINESS INFORMATION\n")
        f.write("-" * 20 + "\n")
        f.write(f"Business Name: {business_details.get('name', 'N/A')}\n")
        f.write(f"Address: {business_details.get('address', 'N/A')}\n")
        f.write(f"Phone: {business_details.get('phone', 'N/A')}\n")
        f.write(f"Website: {business_details.get('website', 'N/A')}\n")
        f.write(f"Category: {business_details.get('category', 'N/A')}\n")
        f.write(f"Overall Rating: {business_details.get('rating', 'N/A')}\n")
        f.write(f"Total Reviews: {business_details.get('total_reviews', 'N/A')}\n")
        f.write(f"Hours: {business_details.get('hours', 'N/A')}\n\n")
        
        # Reviews
        f.write(f"CUSTOMER REVIEWS ({len(reviews)} reviews)\n")
        f.write("-" * 30 + "\n\n")
        
        for i, review in enumerate(reviews, 1):
            f.write(f"Review #{i}\n")
            f.write(f"Author: {review['author']}\n")
            f.write(f"Rating: {review['rating']}⭐\n")
            f.write(f"Date: {review['date']}\n")
            f.write(f"Review: {review.get('text', 'No text provided')}\n")
            f.write("-" * 50 + "\n\n")
    
    return filepath

def scrape_and_analyze(url, days, custom_date, email, session_id):
    driver = init_driver()

    try:
        socketio.emit('status_update', {
                      'progress': 5, 'status': 'Loading Google Maps page...'}, room=session_id)
        driver.get(url)
        time.sleep(3)

        socketio.emit('status_update', {
                      'progress': 8, 'status': 'Extracting business information...'}, room=session_id)
        
        business_details = extract_business_details(driver)
        
        # Emit business details to frontend (with URL for compatibility)
        socketio.emit('business_details', {
            'url': url,
            'businessDetails': business_details
        }, room=session_id)

        if custom_date:
            cutoff_date = datetime.datetime.strptime(custom_date, "%Y-%m-%d")
        else:
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=int(days))

        socketio.emit('status_update', {
                      'progress': 10, 'status': 'Finding Reviews tab...'}, room=session_id)

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
            socketio.emit('status_update', {
                          'progress': 0, 'status': 'Could not find Reviews tab', 'error': True}, room=session_id)
            driver.quit()
            return

        socketio.emit('status_update', {
                      'progress': 20, 'status': 'Setting up sort by newest...'}, room=session_id)

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
                    sort_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, selector)))
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
                        newest_option = WebDriverWait(driver, 3).until(
                            EC.element_to_be_clickable((By.XPATH, selector)))
                        driver.execute_script(
                            "arguments[0].click();", newest_option)
                        print("[↕️ SORT] Clicked on 'Newest'")
                        time.sleep(3)
                        break
                    except:
                        continue
        except Exception as e:
            print("[⚠️ WARN] Could not set sort order:", str(e))

        socketio.emit('status_update', {
                      'progress': 30, 'status': 'Scrolling to load reviews...'}, room=session_id)

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

        print(
            f"[🎯 TARGET] Looking for reviews newer than {cutoff_date.date()}")

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

            review_blocks = []

            # Method 1: Look for divs with review-related attributes
            try:
                review_blocks = driver.find_elements(
                    By.CSS_SELECTOR, 'div[data-review-id]')
                print(
                    f"[🔍 METHOD1] Found {len(review_blocks)} reviews with data-review-id")
            except:
                pass

            # Method 2: If method 1 fails, try broader selectors
            if not review_blocks:
                try:
                    review_blocks = driver.find_elements(
                        By.CSS_SELECTOR, 'div.jftiEf')
                    print(
                        f"[🔍 METHOD2] Found {len(review_blocks)} reviews with jftiEf class")
                except:
                    pass

            # Method 3: Even broader approach
            if not review_blocks:
                try:
                    # Look for elements that contain both author and rating
                    review_blocks = driver.find_elements(
                        By.XPATH, "//div[.//span[@class='d4r55'] and .//span[contains(@class,'kvMYJc')]]")
                    print(
                        f"[🔍 METHOD3] Found {len(review_blocks)} reviews with XPath")
                except:
                    pass

            # Method 4: Last resort - look for any div containing review-like content
            if not review_blocks:
                try:
                    review_blocks = driver.find_elements(
                        By.XPATH, "//div[.//span[@class='rsqaWe']]")
                    print(
                        f"[🔍 METHOD4] Found {len(review_blocks)} reviews with date elements")
                except:
                    pass

            if not review_blocks:
                print("[❌ ERROR] No review blocks found with any method")
                stale_scrolls += 1
                continue

            print(
                f"[🔄 SCROLL {scroll_count + 1}] Found {len(review_blocks)} review blocks")

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
                                temp_text_elem = block.find_element(
                                    By.CSS_SELECTOR, ".MyEned, .wiI7pd")
                                temp_text = temp_text_elem.text[:50]
                            except:
                                pass

                            # Get author and date for ID
                            temp_author = ""
                            temp_date = ""
                            try:
                                temp_author_elem = block.find_element(
                                    By.CSS_SELECTOR, ".d4r55")
                                temp_author = temp_author_elem.text
                            except:
                                pass
                            try:
                                temp_date_elem = block.find_element(
                                    By.CSS_SELECTOR, '.rsqaWe')
                                temp_date = temp_date_elem.text
                            except:
                                pass

                            # Create unique ID from available data
                            review_id = f"{temp_author}_{temp_date}_{temp_text}".replace(
                                " ", "_").replace("\n", "")[:100]

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
                    date_selectors = ['.rsqaWe',
                                      '.DU9Pgb', 'span[class*="rsqaWe"]']
                    for date_selector in date_selectors:
                        try:
                            date_element = block.find_element(
                                By.CSS_SELECTOR, date_selector)
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
                    author_selectors = [".d4r55", ".YBMEb",
                                        "div[data-href*='contrib']"]
                    for author_selector in author_selectors:
                        try:
                            author_element = block.find_element(
                                By.CSS_SELECTOR, author_selector)
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
                        rating_element = block.find_element(
                            By.CSS_SELECTOR, "span[class*='kvMYJc']")
                        aria_label = rating_element.get_attribute("aria-label")
                        rating_match = re.search(
                            r'(\d+(?:\.\d+)?)', aria_label)
                        if rating_match:
                            rating = float(rating_match.group(1))
                    except:
                        try:
                            # Method 2: count filled stars
                            stars = block.find_elements(
                                By.CSS_SELECTOR, "span[style*='width']")
                            if stars:
                                style = stars[0].get_attribute("style")
                                width_match = re.search(
                                    r'width:\s*(\d+)%', style)
                                if width_match:
                                    rating = float(width_match.group(
                                        1)) / 20  # 100% = 5 stars
                        except:
                            # Method 3: look for star elements
                            try:
                                star_elements = block.find_elements(
                                    By.CSS_SELECTOR, ".kvMYJc")
                                rating = len(star_elements)
                            except:
                                pass

                    # Extract review text with multiple selectors
                    text = ""
                    text_selectors = [".MyEned", ".wiI7pd",
                                      "span[jsaction*='expand']", ".review-text"]
                    for text_selector in text_selectors:
                        try:
                            text_element = block.find_element(
                                By.CSS_SELECTOR, text_selector)
                            text = text_element.text.strip()
                            break
                        except:
                            continue

                    try:
                        photo_elements = block.find_elements(By.CSS_SELECTOR, 'img')
                        review_photos = [
                            img.get_attribute("src") 
                            for img in photo_elements 
                            if 'googleusercontent.com' in img.get_attribute("src") and 'photo.jpg' in img.get_attribute("src")
                        ]
                    except:
                        review_photos = []


                    review = {
                        "author": author,
                        "rating": rating,
                        "date": parsed_date.strftime("%Y-%m-%d"),
                        "text": text,
                        "photo": review_photos
                    }

                    reviews.append(review)
                    processed_review_ids.add(review_id)
                    new_reviews_found = True
                    reviews_processed_this_scroll += 1

                    if session_id not in SESSIONS:
                        SESSIONS[session_id] = []
                    SESSIONS[session_id].append(review)

                    # Emit individual review to frontend (with URL for compatibility)
                    print(
                        f"[🔄 EMIT] Emitting review to session {session_id}: {review['author']}")
                    socketio.emit('review', {
                        'url': url,
                        'reviews': [review]
                    }, room=session_id)
                    print(
                        f"[✅ NEW] Processed review from {author} ({parsed_date.date()}) - Rating: {rating}")

                    time.sleep(0.1)

                except Exception as e:
                    print(f"[⚠️ EXTRACT] Error extracting review: {e}")
                    continue

            print(
                f"[📊 STATS] Scroll {scroll_count + 1}: Processed {reviews_processed_this_scroll} new reviews, Total: {len(reviews)}")

            # Update progress and status
            progress = min(90, 30 + (scroll_count * 60 / max_scrolls))
            socketio.emit('status_update', {
                'progress': progress,
                'status': f'Found {len(reviews)} reviews... (scroll {scroll_count + 1}, found {reviews_processed_this_scroll} this round)'
            }, room=session_id)

            if new_reviews_found:
                stale_scrolls = 0
                print(
                    f"[📈 PROGRESS] Total reviews: {len(reviews)}, This scroll: {reviews_processed_this_scroll}")
            else:
                stale_scrolls += 1
                print(
                    f"[🌀 STALE] No new reviews. Stale count: {stale_scrolls}/{max_stale_scrolls}")

            if stale_scrolls >= max_stale_scrolls:
                print(
                    f"[🛑 STOP] Stopping due to {max_stale_scrolls} consecutive scrolls without new reviews")
                break

            if reviews_processed_this_scroll > 0:
                stale_scrolls = 0
                new_reviews_found = True
                print(
                    f"[✅ ACTIVE] Found {reviews_processed_this_scroll} new reviews this scroll")
            else:
                stale_scrolls += 1
                print(
                    f"[🌀 STALE] No new reviews found. Stale count: {stale_scrolls}/{max_stale_scrolls}")

            # Check if we should continue
            if stale_scrolls >= max_stale_scrolls:
                print(
                    f"[🛑 STOP] Stopping due to {max_stale_scrolls} consecutive scrolls without new reviews")
                break

            try:
                scrollable = driver.find_element(
                    By.CSS_SELECTOR, "div.m6QErb.DxyBCb.kA9KIf.dS8AEf")
                driver.execute_script(
                    "arguments[0].scrollTop = arguments[0].scrollHeight", scrollable)
                print(
                    f"[↕️ SCROLL {scroll_count}] Scrolled review container to bottom")
            except Exception as e:
                print(f"[⚠️ SCROLL] Failed to scroll review container: {e}")

            # ⏱ Wait a bit to let reviews load
            time.sleep(random.uniform(2.5, 4.5))

            try:
                more_buttons = driver.find_elements(
                    By.CSS_SELECTOR, 'button[jsaction="pane.review.expandReview"]')
                for btn in more_buttons:
                    driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.2)
            except Exception as e:
                print(f"[⚠️ MORE] Could not expand reviews: {e}")

            scroll_count += 1

        # Store results in session for compatibility with new format
        SESSIONS[session_id] = {
            url: {
                'businessDetails': business_details,
                'reviews': reviews,
                'sentiment': '',
                'swot': {}
            }
        }

        driver.quit()

        if not reviews:
            socketio.emit('status_update', {
                          'progress': 100, 'status': 'No reviews found in the specified date range'}, room=session_id)
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


def scrape_bulk_and_analyze(urls, days, custom_date, email, session_id):
    """Scrape and analyze multiple URLs"""
    print(f"[🚀 BULK] Starting bulk scraping for {len(urls)} URLs")
    
    # Initialize results storage
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {}
    
    total_urls = len(urls)
    completed_urls = 0
    
    for i, url in enumerate(urls):
        if not ACTIVE_JOBS.get(session_id, True):
            print(f"[🛑 CANCELLED] Bulk scraping cancelled by user")
            break
            
        print(f"[📊 PROGRESS] Processing URL {i+1}/{total_urls}: {url}")
        
        # Update progress
        progress = (i / total_urls) * 100
        socketio.emit('status_update', {
            'progress': progress,
            'status': f'Processing business {i+1} of {total_urls}...'
        }, room=session_id)
        
        try:
            # Initialize driver for this URL
            driver = init_driver()
            
            # Extract business details
            business_details = extract_business_details(driver)
            
            # Emit business details
            socketio.emit('business_details', {
                'url': url,
                'businessDetails': business_details
            }, room=session_id)
            
            # Scrape reviews for this URL
            reviews = []
            processed_review_ids = set()
            scroll_count = 0
            max_scrolls = 20
            stale_scrolls = 0
            max_stale_scrolls = 3
            
            # Navigate to reviews
            reviews_url = url.replace('/maps/place/', '/maps/place/') + '/reviews'
            driver.get(reviews_url)
            time.sleep(3)
            
            # Scroll and collect reviews
            while scroll_count < max_scrolls and stale_scrolls < max_stale_scrolls:
                review_blocks = driver.find_elements(By.CSS_SELECTOR, '[data-review-id]')
                new_reviews_found = False
                reviews_processed_this_scroll = 0
                
                for block in review_blocks:
                    try:
                        review_id = block.get_attribute('data-review-id')
                        if review_id in processed_review_ids:
                            continue
                            
                        # Extract review data
                        author = block.find_element(By.CSS_SELECTOR, '.d4r55').text.strip()
                        rating_element = block.find_element(By.CSS_SELECTOR, '.kvMYJc')
                        rating = len(rating_element.find_elements(By.CSS_SELECTOR, '.QqG1Sd'))
                        
                        # Parse date
                        date_text = block.find_element(By.CSS_SELECTOR, '.rsqaWe').text.strip()
                        parsed_date = parse_relative_date(date_text)
                        
                        # Check date filter
                        if days != 'custom':
                            days_int = int(days)
                            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days_int)
                            if parsed_date < cutoff_date:
                                continue
                        elif custom_date:
                            cutoff_date = datetime.datetime.strptime(custom_date, '%Y-%m-%d')
                            if parsed_date < cutoff_date:
                                continue
                        
                        # Extract review text
                        text = ''
                        text_selectors = [".wiI7pd", "span[jsaction*='expand']", ".review-text"]
                        for text_selector in text_selectors:
                            try:
                                text_element = block.find_element(By.CSS_SELECTOR, text_selector)
                                text = text_element.text.strip()
                                break
                            except:
                                continue
                        
                        # Extract photos
                        try:
                            photo_elements = block.find_elements(By.CSS_SELECTOR, 'img')
                            review_photos = [
                                img.get_attribute("src") 
                                for img in photo_elements 
                                if 'googleusercontent.com' in img.get_attribute("src") and 'photo.jpg' in img.get_attribute("src")
                            ]
                        except:
                            review_photos = []
                        
                        review = {
                            "author": author,
                            "rating": rating,
                            "date": parsed_date.strftime("%Y-%m-%d"),
                            "text": text,
                            "photo": review_photos
                        }
                        
                        reviews.append(review)
                        processed_review_ids.add(review_id)
                        new_reviews_found = True
                        reviews_processed_this_scroll += 1
                        
                        # Emit individual review
                        socketio.emit('review', {
                            'url': url,
                            'reviews': [review]
                        }, room=session_id)
                        
                    except Exception as e:
                        print(f"[⚠️ EXTRACT] Error extracting review: {e}")
                        continue
                
                # Update progress
                if new_reviews_found:
                    stale_scrolls = 0
                else:
                    stale_scrolls += 1
                
                # Scroll for more reviews
                try:
                    scrollable = driver.find_element(By.CSS_SELECTOR, "div.m6QErb.DxyBCb.kA9KIf.dS8AEf")
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scrollable)
                    time.sleep(random.uniform(2.5, 4.5))
                except:
                    break
                
                scroll_count += 1
            
            # Store results for this URL
            SESSIONS[session_id][url] = {
                'businessDetails': business_details,
                'reviews': reviews,
                'sentiment': '',
                'swot': {}
            }
            
            completed_urls += 1
            print(f"[✅ COMPLETE] URL {i+1}/{total_urls} completed: {len(reviews)} reviews")
            
            driver.quit()
            
        except Exception as e:
            print(f"[❌ ERROR] Failed to process URL {url}: {e}")
            # Store empty results for failed URL
            SESSIONS[session_id][url] = {
                'businessDetails': {},
                'reviews': [],
                'sentiment': '',
                'swot': {}
            }
            completed_urls += 1
            if driver:
                driver.quit()
    
    # Final progress update
    socketio.emit('status_update', {
        'progress': 100,
        'status': f'Bulk analysis complete! Processed {completed_urls} businesses.'
    }, room=session_id)
    
    print(f"[🎉 BULK COMPLETE] Bulk scraping finished. Processed {completed_urls}/{total_urls} URLs")


@app.route('/api/download-csv/<session_id>', methods=['GET'])
def download_csv(session_id):
    results = SESSIONS.get(session_id, {})
    if not results:
        return jsonify({'error': 'No data'}), 404

    # Handle both old and new format
    if isinstance(results, list):
        # Old format - single URL
        reviews = results
        si = StringIO()
        writer = csv.DictWriter(
            si, fieldnames=['date', 'author', 'rating', 'text', 'photo'])
        writer.writeheader()
        writer.writerows(reviews)
        si.seek(0)
        return send_file(
            StringIO(si.read()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'reviews_{session_id}.csv'
        )
    else:
        # New format - multiple URLs
        return generate_bulk_csv(results, session_id)

@app.route('/api/download-pdf/<session_id>', methods=['GET'])
def download_pdf(session_id):
    results = SESSIONS.get(session_id, {})
    
    if not results:
        return jsonify({'error': 'No data'}), 404
    
    try:
        # Handle both old and new format
        if isinstance(results, list):
            # Old format - single URL
            reviews = results
            business_details = SESSIONS.get(f"{session_id}_business", {})
            filepath = generate_pdf_report(business_details, reviews, session_id)
            return send_file(filepath, as_attachment=True, download_name=f'business_report_{session_id}.pdf')
        else:
            # New format - multiple URLs
            return generate_bulk_pdf(results, session_id)
    except Exception as e:
        return jsonify({'error': f'Failed to generate PDF: {str(e)}'}), 500

@app.route('/api/download-txt/<session_id>', methods=['GET'])
def download_txt(session_id):
    results = SESSIONS.get(session_id, {})
    
    if not results:
        return jsonify({'error': 'No data'}), 404
    
    try:
        # Handle both old and new format
        if isinstance(results, list):
            # Old format - single URL
            reviews = results
            business_details = SESSIONS.get(f"{session_id}_business", {})
            filepath = generate_txt_report(business_details, reviews, session_id)
            return send_file(filepath, as_attachment=True, download_name=f'business_report_{session_id}.txt')
        else:
            # New format - multiple URLs
            return generate_bulk_txt(results, session_id)
    except Exception as e:
        return jsonify({'error': f'Failed to generate TXT: {str(e)}'}), 500


@app.route('/api/download-bulk/<session_id>', methods=['POST'])
def download_bulk_results(session_id):
    data = request.get_json()
    results = data.get('results', {})
    format_type = data.get('format', 'csv').lower()
    email = data.get('email', '')
    
    if not results:
        return jsonify({'error': 'No results data'}), 404
    
    try:
        if format_type == 'csv':
            return generate_bulk_csv(results, session_id)
        elif format_type == 'pdf':
            return generate_bulk_pdf(results, session_id)
        elif format_type == 'txt':
            return generate_bulk_txt(results, session_id)
        else:
            return jsonify({'error': 'Invalid format. Use csv, pdf, or txt'}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to generate {format_type.upper()}: {str(e)}'}), 500


@app.route('/api/send-email', methods=['POST'])
def send_email_results():
    data = request.get_json()
    results = data.get('results', {})
    email = data.get('email', '')
    session_id = data.get('sessionId', '')
    
    if not results:
        return jsonify({'error': 'No results data'}), 404
    
    if not email:
        return jsonify({'error': 'Email address required'}), 400
    
    try:
        # Generate email content
        email_content = generate_email_content(results, session_id)
        
        # Here you would integrate with your email service
        # For now, we'll just return success
        # You can integrate with services like SendGrid, AWS SES, etc.
        
        print(f"[📧 EMAIL] Would send email to {email} with {len(results)} business results")
        
        return jsonify({
            'message': 'Email sent successfully',
            'recipient': email,
            'businesses': len(results)
        })
    except Exception as e:
        return jsonify({'error': f'Failed to send email: {str(e)}'}), 500


def generate_bulk_csv(results, session_id):
    """Generate CSV file with all business results"""
    si = StringIO()
    writer = csv.writer(si)
    
    # Write header
    writer.writerow(['Business Name', 'Address', 'Phone', 'Website', 'Category', 'Rating', 'Total Reviews', 'Hours', 'Review Date', 'Review Author', 'Review Rating', 'Review Text'])
    
    for url, url_results in results.items():
        business_details = url_results.get('businessDetails', {})
        reviews = url_results.get('reviews', [])
        
        if not business_details.get('name'):
            continue
            
        for review in reviews:
            writer.writerow([
                business_details.get('name', ''),
                business_details.get('address', ''),
                business_details.get('phone', ''),
                business_details.get('website', ''),
                business_details.get('category', ''),
                business_details.get('rating', ''),
                business_details.get('total_reviews', ''),
                business_details.get('hours', ''),
                review.get('date', ''),
                review.get('author', ''),
                review.get('rating', ''),
                review.get('text', '')
            ])
    
    si.seek(0)
    return send_file(
        StringIO(si.read()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'google_reviews_analysis_{session_id}.csv'
    )


def generate_bulk_pdf(results, session_id):
    """Generate PDF file with all business results"""
    filepath = f"/tmp/bulk_report_{session_id}.pdf"
    doc = SimpleDocTemplate(filepath, pagesize=letter)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    for i, (url, url_results) in enumerate(results.items(), 1):
        business_details = url_results.get('businessDetails', {})
        reviews = url_results.get('reviews', [])
        
        if not business_details.get('name'):
            continue
            
        # Business section
        story.append(Paragraph(f"Business {i}: {business_details.get('name', 'Unknown')}", title_style))
        story.append(Spacer(1, 12))
        
        # Business details
        details = []
        if business_details.get('address'):
            details.append(f"Address: {business_details['address']}")
        if business_details.get('phone'):
            details.append(f"Phone: {business_details['phone']}")
        if business_details.get('website'):
            details.append(f"Website: {business_details['website']}")
        if business_details.get('rating'):
            details.append(f"Rating: {business_details['rating']}")
        if business_details.get('total_reviews'):
            details.append(f"Total Reviews: {business_details['total_reviews']}")
        
        for detail in details:
            story.append(Paragraph(detail, styles['Normal']))
            story.append(Spacer(1, 6))
        
        story.append(Spacer(1, 12))
        
        # Reviews table
        if reviews:
            story.append(Paragraph("Reviews:", styles['Heading2']))
            story.append(Spacer(1, 12))
            
            table_data = [['Date', 'Author', 'Rating', 'Review']]
            for review in reviews[:50]:  # Limit to first 50 reviews per business
                table_data.append([
                    review.get('date', ''),
                    review.get('author', ''),
                    f"{review.get('rating', '')}⭐",
                    textwrap.shorten(review.get('text', ''), width=100)
                ])
            
            table = Table(table_data, colWidths=[1*inch, 1.5*inch, 0.5*inch, 3*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(table)
        
        story.append(Spacer(1, 20))
        story.append(Paragraph("=" * 50, styles['Normal']))
        story.append(Spacer(1, 20))
    
    doc.build(story)
    return send_file(filepath, as_attachment=True, download_name=f'google_reviews_analysis_{session_id}.pdf')


def generate_bulk_txt(results, session_id):
    """Generate TXT file with all business results"""
    filepath = f"/tmp/bulk_report_{session_id}.txt"
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("GOOGLE REVIEWS ANALYSIS REPORT\n")
        f.write("=" * 50 + "\n\n")
        
        for i, (url, url_results) in enumerate(results.items(), 1):
            business_details = url_results.get('businessDetails', {})
            reviews = url_results.get('reviews', [])
            
            if not business_details.get('name'):
                continue
                
            # Business section
            f.write(f"BUSINESS {i}: {business_details.get('name', 'Unknown')}\n")
            f.write("-" * 40 + "\n")
            
            # Business details
            if business_details.get('address'):
                f.write(f"Address: {business_details['address']}\n")
            if business_details.get('phone'):
                f.write(f"Phone: {business_details['phone']}\n")
            if business_details.get('website'):
                f.write(f"Website: {business_details['website']}\n")
            if business_details.get('rating'):
                f.write(f"Rating: {business_details['rating']}\n")
            if business_details.get('total_reviews'):
                f.write(f"Total Reviews: {business_details['total_reviews']}\n")
            
            f.write("\n")
            
            # Reviews
            if reviews:
                f.write("REVIEWS:\n")
                f.write("-" * 20 + "\n")
                for j, review in enumerate(reviews[:50], 1):  # Limit to first 50 reviews
                    f.write(f"{j}. {review.get('date', '')} - {review.get('author', '')} ({review.get('rating', '')}⭐)\n")
                    f.write(f"   {review.get('text', '')}\n\n")
            
            f.write("\n" + "=" * 50 + "\n\n")
    
    return send_file(filepath, as_attachment=True, download_name=f'google_reviews_analysis_{session_id}.txt')


def generate_email_content(results, session_id):
    """Generate email content for all business results"""
    content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .business {{ margin-bottom: 30px; padding: 20px; border: 1px solid #ddd; border-radius: 8px; }}
            .business h2 {{ color: #2563eb; margin-top: 0; }}
            .details {{ margin: 10px 0; }}
            .reviews {{ margin-top: 15px; }}
            .review {{ margin: 10px 0; padding: 10px; background: #f9f9f9; border-radius: 4px; }}
            .rating {{ color: #f59e0b; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>Google Reviews Analysis Report</h1>
        <p>Session ID: {session_id}</p>
        <p>Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    """
    
    for i, (url, url_results) in enumerate(results.items(), 1):
        business_details = url_results.get('businessDetails', {})
        reviews = url_results.get('reviews', [])
        
        if not business_details.get('name'):
            continue
            
        content += f"""
        <div class="business">
            <h2>Business {i}: {business_details.get('name', 'Unknown')}</h2>
            <div class="details">
        """
        
        if business_details.get('address'):
            content += f"<p><strong>Address:</strong> {business_details['address']}</p>"
        if business_details.get('phone'):
            content += f"<p><strong>Phone:</strong> {business_details['phone']}</p>"
        if business_details.get('website'):
            content += f"<p><strong>Website:</strong> <a href='{business_details['website']}'>{business_details['website']}</a></p>"
        if business_details.get('rating'):
            content += f"<p><strong>Rating:</strong> {business_details['rating']}⭐</p>"
        if business_details.get('total_reviews'):
            content += f"<p><strong>Total Reviews:</strong> {business_details['total_reviews']}</p>"
        
        content += "</div>"
        
        if reviews:
            content += "<div class='reviews'><h3>Reviews:</h3>"
            for review in reviews[:20]:  # Limit to first 20 reviews
                content += f"""
                <div class="review">
                    <p><strong>{review.get('date', '')} - {review.get('author', '')}</strong> 
                    <span class="rating">{review.get('rating', '')}⭐</span></p>
                    <p>{review.get('text', '')}</p>
                </div>
                """
            content += "</div>"
        
        content += "</div>"
    
    content += """
    </body>
    </html>
    """
    
    return content


if __name__ == '__main__':
    # socketio.run(app, port=5000, debug=True)
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5001)))


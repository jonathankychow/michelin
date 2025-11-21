import requests
from bs4 import BeautifulSoup
import time
from typing import List, Tuple, Optional, Dict, Any
from urllib.parse import urljoin, parse_qs, urlparse
import pandas as pd
import re
from datetime import datetime
import os
import time

# Helper function to parse ratings from restaurant card
def _parse_rating(rating_span) -> str:
    rating_text = "No Rating"
    star_count = 0
    if rating_span:
        img_list = rating_span.find_all('img', class_='michelin-award')
        for img in img_list:
            src = img['src']
            if 'bib-gourmand' in src:
                return 'Bib Gourmand'
            elif '1star' in src:
                star_count += 1
        if star_count == 1:
            rating_text = "1 Star"
        elif star_count == 2:
            rating_text = "2 Stars"
        elif star_count == 3:
            rating_text = "3 Stars"

    return rating_text

# Helper function to parse the price and cuisine from restaurant card
def _parse_price_cuisine(footer):
    raw_text = footer.get_text()
    # Remove /n
    cleaned_text = re.sub(r'\s+', ' ', raw_text).strip().replace(" ","").split('·')
    return cleaned_text[0], cleaned_text[1]

# Helper function to parse google maps iframe in restaurant page
def _scrape_gm_iframe_url(url: str):
    # Parse url
    parsed_url = urlparse(url)

    # Extract the query parameters into a dictionary
    query_params = parse_qs(parsed_url.query)

    if 'q' in query_params:
        # 3. Get the value of the 'query' key and split it
        lat_lon_string = query_params['q'][0]
        lat_lon = lat_lon_string.split(',')

        latitude = float(lat_lon[0])
        longitude = float(lat_lon[1])
    else:
        latitude, longitude = "", ""

    return latitude, longitude

# Helper function to scrape data from restaurant page
def _scrape_restaurant_page(url: str, headers: dict):
    # Query URL
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"\tError fetching page: {e}")
        return {
            "Address": "",
            "Description": "",
            "Coordinates": "",
            "Website URL": ""
        }

    # Initialize parser
    soup = BeautifulSoup(response.text, 'html.parser')

    # Get address
    address_tag = soup.select_one('div.data-sheet__block--text')
    address = address_tag.get_text(strip=True) if address_tag else ""

    # Get description
    description_tag = soup.select_one('div.data-sheet__description')
    description = description_tag.get_text(strip=True) if description_tag else ""

    # Get restaurant url
    restaurant_website_tag = soup.find('a',{'data-event': 'CTA_website'})
    restaurant_website = restaurant_website_tag['href'] if restaurant_website_tag else ""

    # Get restaurant phone number
    restaurant_telephone_tag = soup.find('a',{'data-event': 'CTA_tel'})
    restaurant_telephone = str.split(restaurant_telephone_tag['href'], ':')[1] if restaurant_telephone_tag else ""

    # Get reservation link
    reservation_link_tag = soup.find('a', class_='js-restaurant-book-btn')
    reservation_link = reservation_link_tag['href'] if reservation_link_tag else ""

    # Get coordinates
    iframe_url = soup.select('iframe')[1]['src']
    latitude, longitude = _scrape_gm_iframe_url(iframe_url)

    return {
        "Address": address,
        "Description": description,
        "Restaurant Website": restaurant_website,
        "Telephone Number": restaurant_telephone,
        "Reservation Link": reservation_link,
        "Latitude": latitude,
        "Longitude": longitude
    }

# Helper function to scrape data from a single web page
def _scrape_results_single_page(url: str, headers: dict) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """
    Helper function to scrape restaurant data and find the next page URL.
    Returns: (List of restaurant dictionaries, Next page URL or None)
    """
    print(f"Scraping page: {url}")

    restaurant_data = []
    next_page_url = None

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching page: {e}")
        return [], None

    soup = BeautifulSoup(response.text, 'html.parser')

    # 1. Identify all restaurant cards (The anchor tag containing all details)
    # This selector targets the main link element for each restaurant card.
    restaurant_cards = soup.select('div.card__menu')

    if not restaurant_cards:
        print("No restaurant cards found. Stopping page scrape.")

    for card in restaurant_cards:
        # Parse name
        name_tag = card.select_one('h3.card__menu-content--title')
        name = name_tag.get_text(strip=True) if name_tag else ""

        # Filter out 4 DC restaurants that appear in each page for some reason
        if name in ['La\'Shukran', 'Café Riggs', 'Xiquet', 'Rooster & Owl']:
            continue

        # Print name of restaurant being parsed
        print(f"\t{name}")

        # Parse footer
        footer = card.select('div.card__menu-footer--score')
        city = footer[0].get_text(strip=True) if footer[0] else ""
        price, cuisine = _parse_price_cuisine(footer[1])

        # Parse rating
        rating_span = card.select_one('span.distinction-icon')
        rating = _parse_rating(rating_span)

        # Parse restaurant URL
        restaurant_url = "https://guide.michelin.com" + card.select_one('a')['href']
        restaurant_page_data = _scrape_restaurant_page(restaurant_url, headers)

        restaurant_data.append({
            "Name": name,
            "Rating": rating,
            "City": city,
            "Price Range": price,
            "Cuisine": cuisine,
            "Description": restaurant_page_data['Description'],
            "Address": restaurant_page_data['Address'],
            "Latitude": restaurant_page_data['Latitude'],
            "Longitude": restaurant_page_data['Longitude'],
            "Michelin Website": restaurant_url,
            "Restaurant Website": restaurant_page_data['Restaurant Website'],
            "Restaurant Telephone Number": restaurant_page_data['Telephone Number'],
            "Reservation Link": restaurant_page_data['Reservation Link'],
        })

    # 2. Extract 'Next Page' URL (Robust Logic for Pagination)
    pagination_links = soup.select('ul.pagination li a')
    next_link_element = None

    # Look for the link that contains the right arrow icon (fa-angle-right)
    for link in pagination_links:
        if link.select_one('i.fa-angle-right'):
            next_link_element = link
            break

    if next_link_element:
        relative_link = next_link_element.get('href')

        if relative_link and relative_link != '#':
            new_full_url = urljoin(url, relative_link)

            # CRITICAL CHECK: Only proceed if the new URL is genuinely different
            if new_full_url != url:
                next_page_url = new_full_url
                print(f"\tPotential next URL found: {next_page_url}")
            else:
                print("\tNext link points to the current URL. Reached the last page.")

    return restaurant_data, next_page_url


# Main scraper function
def scrape_michelin_data(start_url: str) -> pd.DataFrame:
    """
    Scrapes restaurant data (Name, City, Rating, Address) from all pages
    of a given Michelin Guide URL and returns a Pandas DataFrame.
    """
    print(f"Scraping {start_url}")

    # Define Request Headers once
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    all_restaurants_list = []
    current_url = start_url
    page_count = 1

    # Loop as long as a 'current_url' is valid (i.e., we found a next page)
    while current_url:
        print(f"\n--- Processing Page {page_count} ---")

        # Use the helper function for the single page scrape
        restaurant_list_on_page, next_url = _scrape_results_single_page(current_url, HEADERS)

        if not restaurant_list_on_page and page_count == 1:
            print("Initial page failed to extract data. Cannot continue.")
            break
        elif not restaurant_list_on_page:
            # We assume we have reached an empty page, which can happen at the very end
            print("Found no data on the last presumed page. Stopping.")
            break

        all_restaurants_list.extend(restaurant_list_on_page)

        # Update the URL for the next iteration
        current_url = next_url
        page_count += 1

        # CRITICAL: Rate Limiting
        if current_url:
            print("Loading next page...")
            time.sleep(2)

    # Convert the final list of dictionaries into a DataFrame
    df = pd.DataFrame(all_restaurants_list)
    return df


if __name__ == "__main__":
    start_time = time.perf_counter()
    # URL to scrape (use a region with multiple pages for testing the loop)
    # The default URL often has only one page, so switching to a major city like New York
    TARGET_URL = "https://guide.michelin.com/us/en/kyoto-region/restaurants"
    CITY_NAME = 'Kyoto'

    results_df = scrape_michelin_data(TARGET_URL)

    if not results_df.empty:
        print(f"\n=== FINAL RESULTS: Found {len(results_df)} Total Restaurants ===")
        # Display the first few rows of the DataFrame
        print(results_df.head(5).to_markdown(index=False))
    else:
        print(f"\nNo data extracted or DataFrame is empty.")

    # Save outputs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{CITY_NAME}_Michelin_Guide_{timestamp}.xlsx"
    results_df.to_excel(os.path.join("/Users/jonathanchow/Downloads", filename), index=False)

    # Timer
    end_time = time.perf_counter()
    elapsed_time = end_time - start_time
    print(f"Execution took {elapsed_time:.4f} seconds.")
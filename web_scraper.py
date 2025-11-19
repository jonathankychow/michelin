import requests
from bs4 import BeautifulSoup
import time
from typing import List, Tuple, Optional, Dict, Any
from urllib.parse import urljoin
import pandas as pd
import re


# --- Helper Function for Single Page Scraping ---

def _parse_rating(rating_span) -> str:
    rating_text = "No Rating"
    if rating_span:
        image_source = rating_span.select_one('img.michelin-award').get('src', '')
        if '1star' in image_source:
            rating_text = "1 Star"
        elif '2stars' in image_source:
            rating_text = "2 Stars"
        elif '3stars' in image_source:
            rating_text = "3 Stars"
        elif 'bib-gourmand' in image_source:
            rating_text = "Bib Gourmand"
        elif 'plate' in image_source:
            rating_text = "The Plate"

    return rating_text

def _parse_price_cuisine(footer):
    raw_text = footer.get_text()
    # Remove /n
    cleaned_text = re.sub(r'\s+', ' ', raw_text).strip().replace(" ","").split('·')
    return cleaned_text[0], cleaned_text[1]

def _scrape_single_page(url: str, headers: dict) -> Tuple[List[Dict[str, str]], Optional[str]]:
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
    restaurant_cards = soup.select('div.card__menu-content')

    if not restaurant_cards:
        print("No restaurant cards found. Stopping page scrape.")

    for card in restaurant_cards:
        # Parse name
        name_tag = card.select_one('h3.card__menu-content--title')
        name = name_tag.get_text(strip=True) if name_tag else "N/A"

        # Parse footer
        footer = card.select('div.card__menu-footer--score')
        city = footer[0].get_text(strip=True) if footer[0] else ""
        price, cuisine = _parse_price_cuisine(footer[1])

        # Parse rating
        rating_span = card.select_one('span.distinction-icon')
        rating = _parse_rating(rating_span)

        # Parse restaurant URL

        restaurant_data.append({
            "Name": name,
            "Rating": rating,
            "City": city,
            "Price Range": price,
            "Cuisine": cuisine,
            "Description": "",
            "Address": "",
            "Coordinates": "",
            "Michelin URL": "",
            "Website URL": ""
        })

    print(f"   Found {len(restaurant_data)} names and details on this page.")

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
                print(f"   Potential next URL found: {next_page_url}")
            else:
                print("   Next link points to the current URL. Reached the last page.")

    return restaurant_data, next_page_url


# --- Main Scraper Function ---

def scrape_michelin_data(start_url: str) -> pd.DataFrame:
    """
    Scrapes restaurant data (Name, City, Rating, Address) from all pages
    of a given Michelin Guide URL and returns a Pandas DataFrame.
    """
    print(f"Starting multi-page scrape from: {start_url}")

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
        restaurant_list_on_page, next_url = _scrape_single_page(current_url, HEADERS)

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
            print("Sleeping for 2 seconds to be polite to the server...")
            time.sleep(2)

    # Convert the final list of dictionaries into a DataFrame
    df = pd.DataFrame(all_restaurants_list)
    return df


if __name__ == "__main__":
    # URL to scrape (use a region with multiple pages for testing the loop)
    # The default URL often has only one page, so switching to a major city like New York
    TARGET_URL = "https://guide.michelin.com/us/en/nara-region/restaurants"

    michelin_df = scrape_michelin_data(TARGET_URL)

    if not michelin_df.empty:
        print(f"\n=== FINAL RESULTS: Found {len(michelin_df)} Total Restaurants ===")
        # Display the first few rows of the DataFrame
        print(michelin_df.head(10).to_markdown(index=False))

        # Example of how to use the data:
        # print("\nStar Rating Counts:")
        # print(michelin_df['Rating'].value_counts().to_markdown())

        # Example of saving the data
        # michelin_df.to_csv("michelin_new_york.csv", index=False)
    else:
        print("\nNo data extracted or DataFrame is empty.")
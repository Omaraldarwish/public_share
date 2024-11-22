import os
import logging
import requests
from urllib.parse import urljoin
import concurrent.futures

from bs4 import BeautifulSoup

def fetch_page(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logging.error(f"Failed to fetch {url}: {e}")
        return None

def extract_table_text(table):
    rows = table.find_all('tr')
    table_text = ""
    
    for row in rows:
        cells = row.find_all(['th', 'td'])  # Table headers or data cells
        row_text = "\t".join(cell.get_text(strip=True) for cell in cells)
        table_text += row_text + "\n"
    
    return table_text

def scrape_page(url):
    logging.info(f"Scraping {url}...")

    page_content = fetch_page(url)
    
    if not page_content:
        return [], [], "", []
    
    soup = BeautifulSoup(page_content, 'html.parser')

    # extract text
    page_text = soup.get_text(separator=' ', strip=True)

    # extract tables
    tables = soup.find_all('table')
    for table in tables:
        table_text = extract_table_text(table)
        page_text += "\n" + table_text
    
    # extract all images
    def keep_image_src(src):
        if src is None:
            return False
        keywords = ['facebook', 'twitter', 'instagram', 'blog', 'logo', 'world']
        return not any(keyword in src.lower() for keyword in keywords)
            
    images = [urljoin(url, img['src']) for img in soup.find_all('img', src=True)]
    images = [img for img in images if keep_image_src(img)]
    images = list(set(images))  # remove duplicates

    # extract all links
    links = [urljoin(url, a['href']) for a in soup.find_all('a', href=True)]
    links = [link for link in links if link is not None]
    links = list(set(links))  # remove duplicates

    # extract breadcrumb path
    breadcrumbs = soup.find_all(class_='breadcrumb')
    if breadcrumbs:
        breadcrumb_path = breadcrumbs[0].get_text(separator=' > ', strip=True)
        parsed_path = breadcrumb_path.split(' > ')
    else:
        breadcrumb_path = ""
        parsed_path = []

    return links, images, page_text, parsed_path

def scrape(start_url, max_depth, url_prefix, num_workers):
    urls_to_scrape = [(start_url, 0)]
    visited_urls = set()
    out = []

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=num_workers)

    while urls_to_scrape:
        logging.info(f"queue size: {len(urls_to_scrape)}")

        # dedup urls to scrape
        new_urls_to_scrape = []
        _url_cache = set()

        for url, depth in urls_to_scrape:
            if url not in _url_cache and url not in visited_urls:
                new_urls_to_scrape.append((url, depth))
                _url_cache.add(url)

        urls_to_scrape = new_urls_to_scrape

        # Submit tasks for parallel scraping
        future_to_url = {
            executor.submit(scrape_page, url): (url, depth)
            for url, depth in urls_to_scrape
        }
        urls_to_scrape.clear()

        for future in concurrent.futures.as_completed(future_to_url):
            url, depth = future_to_url[future]

            if depth > max_depth:
                continue

            try:
                new_links, new_images, new_text, new_path = future.result()
            except Exception as e:
                logging.error(f"Error scraping {url}: {e}")
                continue

            visited_urls.add(url)

            out.append({
                'url': url,
                'text': new_text,
                'images': new_images,
                'path': new_path,
            })

            # filter out links
            new_links = [
                link for link in new_links
                if (
                    link.startswith(url_prefix)
                    and link not in visited_urls
                )
            ]

            urls_to_scrape.extend((link, depth + 1) for link in new_links)

    return out

def to_txt_file(text, filename):
    with open(filename, 'w') as f:
        f.write(text)

def save_scraped_data(scraped_dicts, output_dir):
    for entry in scraped_dicts:
        filename = "_".join(entry['path']) + ".txt"
        filename = filename.replace('/', '_')
        filename = os.path.join(output_dir, filename)

        with open(filename, 'w') as f:
            f.write(entry['text'])

def start_scraping(start_url, max_depth, url_prefix, num_workers, log_filename):
    # set up logging
    if os.path.exists(log_filename):
        os.remove(log_filename)
    logging.basicConfig(filename=log_filename, level=logging.INFO, format='%(asctime)s - %(message)s')

    # scrape
    return scrape(start_url, max_depth, url_prefix, num_workers)
    
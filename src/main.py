import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Optional
from zipfile import ZipFile

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.wait import WebDriverWait
from tqdm import tqdm

from src.config import tracks_location


def __get_page_data(session: requests.Session, url: str) -> dict:
    soup = BeautifulSoup(session.get(url).content, 'lxml')
    return json.loads(soup.find('div', id='pagedata')['data-blob'])


def __download(session: requests.Session, url: str) -> str:
    page_data = __get_page_data(session, url)
    digital_item = page_data['digital_items'][0]
    subdir = f'{digital_item["artist"]} - {digital_item["title"]}'
    download_dir = f'{tracks_location}/{subdir}'
    done_file = f'{download_dir}/.done'
    if os.path.isfile(done_file):
        return download_dir
    shutil.rmtree(download_dir, ignore_errors=True)
    os.makedirs(download_dir)
    response = session.get(digital_item['downloads']['flac']['url'], stream=True)
    content_disposition = response.headers.get('content-disposition')
    filename = content_disposition.split('filename="')[-1].split('";')[0]
    download_path = f'{download_dir}/{filename}'
    with open(download_path, 'wb') as file:
        for chunk in response.iter_content(chunk_size=8192):
            file.write(chunk)

    if download_path.endswith('.zip'):
        with ZipFile(download_path, 'r') as zipped:
            zipped.extractall(download_dir)
        os.remove(download_path)

    with open(done_file, 'w', encoding='utf8') as done:
        done.write('')

    return download_dir


def download(identity_cookie: str) -> None:
    session = requests.session()
    session.cookies.set('identity', identity_cookie)
    page_data = __get_page_data(session, 'https://bandcamp.com')
    fan = page_data['identities']['fan']
    page_data = __get_page_data(session, f'https://bandcamp.com/{fan["username"]}')
    hidden_sale_ids = [f'{x["sale_item_type"]}{x["sale_item_id"]}' for x in page_data['item_cache']['hidden'].values()]
    collection_data = page_data['collection_data']
    download_urls = [value for key, value in collection_data['redownload_urls'].items() if key not in hidden_sale_ids]
    last_token = collection_data['last_token']
    while True:
        data = session.post(
            'https://bandcamp.com/api/fancollection/1/collection_items',
            json={
                'fan_id': fan['id'],
                'older_than_token': last_token
            }
        ).json()
        download_urls += [
            value for key, value
            in data['redownload_urls'].items()
            if key not in hidden_sale_ids
        ]
        if not data['more_available']:
            break
        last_token = data['last_token']

    with tqdm(total=len(download_urls), desc='Downloading') as progress:
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(lambda x: __download(session, x), url) for url in download_urls]
            for future in futures:
                def __callback(_future):
                    progress.write(_future.result())
                    progress.update(1)

                future.add_done_callback(__callback)
            for future in futures:
                future.result()


def login() -> Optional[str]:
    options = Options()
    options.add_argument('user-data-dir=~/Library/Application Support/Google/Chrome/')
    driver = webdriver.Chrome(options=options)
    driver.get('https://bandcamp.com/login')

    try:
        WebDriverWait(driver, sys.maxsize).until(lambda _driver: bool(_driver.get_cookie('identity')))
    except:
        driver.quit()
        return None
    identity_cookie = driver.get_cookie('identity')['value']
    driver.quit()
    return identity_cookie


def main():
    identity_cookie = login()
    if not identity_cookie:
        print('Did not successfully login')
        return
    download(identity_cookie)


if __name__ == '__main__':
    main()

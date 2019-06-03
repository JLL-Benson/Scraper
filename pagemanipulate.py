from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from utility_commons import *


_DEFAULT_PREFERENCE = {
    'browser.download.folderList': 2,
    'browser.download.manager.showWhenStarting': False,
    # 'browser.download.dir': DOWNLOAD_PATH,
    'browser.download.manager.closeWhenDone': True,
    'browser.download.manager.focusWhenStarting': False,
    'browser.helperApps.neverAsk.saveToDisk': 'text/csv/xls/xlsx'
}

logger = getLogger('scrapy')


class Page:

    def __init__(self, url, pageLoadStrategy='eager', **preference):
        self.desired_capabilities = DesiredCapabilities.FIREFOX
        self.desired_capabilities["pageLoadStrategy"] = pageLoadStrategy
        self.options = webdriver.FirefoxOptions()
        self.options.add_argument('-headless')
        if not bool(preference):
            _DEFAULT_PREFERENCE.update(preference)
        self.profile = webdriver.FirefoxProfile()
        for key, value in _DEFAULT_PREFERENCE.items():
            self.profile.set_preference(key, value)

        self.driver = webdriver.Firefox(firefox_options=self.options, firefox_profile=self.profile)
        # self.driver.maximize_window()
        self.soup = None
        self.driver.get(url)

    def __enter__(self):
        logger.info('Open browser.')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            logger.error('{}, {}, {}'.format(exc_type, exc_val, exc_tb))
        self.close()

    def exist(self, path):
        try:
            tab = self.driver.find_element_by_xpath(path)
            return tab
        except NoSuchElementException as e:
            logging.info('Xpath: {} not exists.'.format(path))
            return False

    def click(self, path):
        try:
            wait = WebDriverWait(self.driver, 1)
            wait.until(EC.element_to_be_clickable((By.XPATH, path)))
            self.driver.find_element_by_xpath(path).click()
            self.soup = self.driver.page_source
            # print(self.soup)
            return self.driver.page_source
        except TimeoutException as e:
            logging.error(e)
            return False

    def send(self, path, value):
        try:
            if self.exist(path):
                self.driver.find_element_by_xpath(path).send_keys(value)

        except Exception as e:
            logging.error(e)

    def close(self):
        self.driver.close()
        logging.info('Browser is closed.')

    def get_requests_cookies(self):
        import requests
        webdriver_cookies = self.driver.get_cookies()
        cookies = requests.cookies.RequestsCookieJar()

        for c in webdriver_cookies:
            cookies.set(c["name"], c['value'])
        return cookies


if __name__ == '__main__':
    url = 'http://210.76.69.38:82/JDGG/QTCGList.aspx?CGLX=A1'
    page = Page(url, 'normal')
    # page.click("//div[@class='content'")
    print(page.driver)
    # print(page.driver.page_source)
    # search_soup = BeautifulSoup(page.driver.page_source, 'lxml')
    #
    # office_list = search_soup.find('div', attrs={'class': 'chengxin'}).find_all('a')
    # print(office_list)
    page.close()




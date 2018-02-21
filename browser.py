'''NOT WORKING
'''
import datetime
import logging
import os
import platform
import sys
import threading
import time
import timeit

if platform.system() == 'Linux':
    from pyvirtualdisplay import Display
from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Include the project package into the system path to allow import
package_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, package_path)

# Import your package (if any) below

log = logging.getLogger(__name__)


class BinanceException(Exception):
    def __init__(self, message='Binance exception occurred.'):
        Exception.__init__(self, message)


class Binance:
    def __init__(self, url='https://www.binance.com/', show_browser=False, browser_type='Chrome', close_browser_on_fail=True, save_screenshot_on_fail=True, logpath='~/Binance/logs'):
        self._stop_all_thread = False
        self.url = url
        self.show_browser = False
        if platform.system() == 'Linux':
            self.show_browser = show_browser
        self.browser_type = browser_type
        self.close_browser_on_fail = close_browser_on_fail
        self.save_screenshot_on_fail = save_screenshot_on_fail
        self.logpath = os.path.expanduser(logpath)  # Expand ~ to home directory's full path
        if not os.path.exists(self.logpath):
            log.debug('Creating {}'.format(self.logpath))
            os.makedirs(self.logpath)
        if not os.path.isdir(self.logpath):
            raise BinanceException('Error, {} is not a directory!'.format(self.logpath))

        # Display properties
        self.browser_width = 1024
        self.browser_height = 768
        if self.show_browser:
            visibility = 1 if self.show_browser else 0
            self.display = Display(visible=visibility, size=(self.browser_width, self.browser_height))

    def __enter__(self):
        log.debug('Enter class')
        self.open(self.url, self.browser_type)
        return self

    def __exit__(self, type, value, traceback):
        '''Context manager that captures any exception during execution.

        We use the context manager to capture any exceptions that might have
        raised during execution.  If an exception raised we will gracefully
        try to take a screenshot & a source code dump.
        '''
        log.debug('Exit class')
        # if type and self.save_screenshot_on_fail:
            # self.save_exception()
        self.close()

    # def get_file_name_path(self, timestamp='', header='screenshot', extension='png'):
        # '''Helper function to create a file name path with timestamp.

        # Helper function to create a file name path with timestamp to save
        # debug info like screen shots.  No file is created only the path is
        # assembled here.
        # '''
        # if not timestamp:
            # timestamp = datetime.datetime.now().isoformat().replace(':', '').replace('-', '').replace('.', '')
        # file_name = '{timestamp}_{header}.{extension}'.format(header=header, timestamp=timestamp, extension=extension)
        # full_path = os.path.join(self.logpath, file_name)
        # return full_path

    # def save_screenshot(self, path):
        # if self.browser:
            # log.debug('Taking screenshot {}'.format(path))
            # self.browser.save_screenshot(path)

    # def dump_source(self, path):
        # if self.browser:
            # log.debug('Dumping sources {}'.format(path))
            # with open(path, mode='w') as f:
                # f.write(self.browser.page_source)

    # def save_exception(self):
        # '''Take a screen shot of a browser web page and dump the sources.

        # Take a screen shot of a browser web page and dump the sources.
        # Normally we'll call this function if an exception was raised for
        # debugging after the facts.  This will fail gracefully.
        # '''
        # timestamp = datetime.datetime.now().isoformat().replace(':', '').replace('-', '').replace('.', '')
        # # Save screenshot
        # try:
            # path = self.get_file_name_path(timestamp=timestamp, header='screenshot', extension='png')
            # self.save_screenshot(path)
        # except:
            # log.warning('Unable to save screenshot')

        # # Save page source
        # try:
            # path = self.get_file_name_path(timestamp=timestamp, header='sources', extension='html')
            # self.dump_source(path)
        # except:
            # log.warning('Unable to save page source')

    # def _switch_to_frame(self):
        # try:
            # WebDriverWait(self.browser, 10).until(EC.alert_is_present(), 'Timed out waiting for PA creation confirmation popup to appear.')
            # alert = self.browser.switch_to_alert()
            # print("Accept alert")
            # alert.accept()
        # except TimeoutException:
            # print("No alert")
        # self.browser.switch_to_frame(self.browser.find_element_by_xpath('//frame'))

    def open(self, url, browser_type='Chrome'):
        if self.show_browser:
            self.display.start()
        log.debug('Open browser with url "{}".'.format(url))

        if browser_type == 'Firefox':
            self.browser = webdriver.Firefox()
        else:
            self.browser = webdriver.Chrome()
        self.browser.get(url)
        self.browser.set_window_position(0, 0)
        self.browser.set_window_size(self.browser_width, self.browser_height)

    def close(self):
        log.debug('Close browser.')
        self._stop_all_thread = True
        if self.close_browser_on_fail:
            self.browser.quit()
        if self.show_browser:
            self.display.stop()

    def set_language(self, lang='en'):
        # Reference: https://stackoverflow.com/questions/7781792/selenium-waitforelement
        div_languages = self.browser.find_element_by_xpath('//div[@class="languages"]')
        log.info('Current language is "{}"'.format(div_languages.text))
        try:
            current_language = div_languages.find_element_by_xpath('//span[@ng-if="cur_lang==\'{}\'"]'.format(lang))
        except NoSuchElementException:
            # Reference: https://stackoverflow.com/questions/8252558/is-there-a-way-to-perform-a-mouseover-hover-over-an-element-using-selenium-and
            ActionChains(self.browser).move_to_element(div_languages).perform()
            li_language = div_languages.find_element_by_xpath('//li[@ng-click="switching(\'{}\')"]'.format(lang))
            li_language.click()
            div_languages = self.browser.find_element_by_xpath('//div[@class="languages"]')
            log.info('Language is set to "{}"'.format(div_languages.text))

    def get_prices(self, my_tickers=None):
        # Get the markets tab
        li_bnb_markets = self.browser.find_element_by_xpath('//div[@class="indexMarkets ng-scope"]//div[@class="container"]//div[@id="markets-table"]//div[@class="container"]//div[@class="f-cb"]//ul[@class="type f-fl"]//li[@ng-class="{true:\'cur\',false:\'\'}[curMarket==\'BNB\']"]')
        li_btc_markets = self.browser.find_element_by_xpath('//div[@class="indexMarkets ng-scope"]//div[@class="container"]//div[@id="markets-table"]//div[@class="container"]//div[@class="f-cb"]//ul[@class="type f-fl"]//li[@ng-class="{true:\'cur\',false:\'\'}[curMarket==\'BTC\']"]')
        li_eth_markets = self.browser.find_element_by_xpath('//div[@class="indexMarkets ng-scope"]//div[@class="container"]//div[@id="markets-table"]//div[@class="container"]//div[@class="f-cb"]//ul[@class="type f-fl"]//li[@ng-class="{true:\'cur\',false:\'\'}[curMarket==\'ETH\']"]')
        li_usdt_markets = self.browser.find_element_by_xpath('//div[@class="indexMarkets ng-scope"]//div[@class="container"]//div[@id="markets-table"]//div[@class="container"]//div[@class="f-cb"]//ul[@class="type f-fl"]//li[@ng-class="{true:\'cur\',false:\'\'}[curMarket==\'USDT\']"]')

        # all_market_pairs = self.browser.find_elements_by_xpath('//div[@class="indexMarkets ng-scope"]//div[@class="container"]//div[@id="markets-table"]//div[@class="container"]//div[@class="con"]//table[@id="products"]//tbody//tr[@class="ng-scope"]')
        # print('all market pairs {}'.format(len(all_market_pairs)))
        li_bnb_markets.click()
        bnb_market_pairs = self.browser.find_elements_by_xpath('//div[@class="indexMarkets ng-scope"]//div[@class="container"]//div[@id="markets-table"]//div[@class="container"]//div[@class="con"]//table[@id="products"]//tbody//tr[@class="ng-scope" and not(@style="display: none;")]')
        print('BNB market pairs {}'.format(len(bnb_market_pairs)))
        li_btc_markets.click()
        btc_market_pairs = self.browser.find_elements_by_xpath('//div[@class="indexMarkets ng-scope"]//div[@class="container"]//div[@id="markets-table"]//div[@class="container"]//div[@class="con"]//table[@id="products"]//tbody//tr[@class="ng-scope" and not(@style="display: none;")]')
        print('BTC market pairs {}'.format(len(btc_market_pairs)))
        li_eth_markets.click()
        eth_market_pairs = self.browser.find_elements_by_xpath('//div[@class="indexMarkets ng-scope"]//div[@class="container"]//div[@id="markets-table"]//div[@class="container"]//div[@class="con"]//table[@id="products"]//tbody//tr[@class="ng-scope" and not(@style="display: none;")]')
        print('ETH market pairs {}'.format(len(eth_market_pairs)))
        li_usdt_markets.click()
        usdt_market_pairs = self.browser.find_elements_by_xpath('//div[@class="indexMarkets ng-scope"]//div[@class="container"]//div[@id="markets-table"]//div[@class="container"]//div[@class="con"]//table[@id="products"]//tbody//tr[@class="ng-scope" and not(@style="display: none;")]')
        print('USDT market pairs {}'.format(len(usdt_market_pairs)))

        for pair in usdt_market_pairs:
            items = pair.find_elements_by_tag_name('td')
            ticker = items[1].text
            price = items[2].text.split('/')[0].strip().replace(',', '')
            tickers_price_history[ticker] = price

        print(tickers_price_history)

if __name__ == '__main__':
    with Binance(browser_type='Firefox', close_browser_on_fail=False) as binance:
        binance.set_language()
        binance.get_prices()
        # monitor specific ticker
        # store history of monitored ticker result in minute(?) segment
        # compare current ticker to history
        # send text to my phone if ticker jumped by a certain percentage

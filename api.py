'''This module uses the API provided by the crypto exchanges to query coin
prices.  An gmail account credenital needs to be defined in the environmental
variables in order to send out notifications to recipients.  The following
variables need to be defined in .bashrc in order for the email function to
work.

# variables for ~/projects/crypto/monitor.py
export GMAIL="<id>@gmail.com"
export GMAIL_PASS="<password>"

The program is running in the background
Reference: https://askubuntu.com/questions/396654/how-to-run-the-python-program-in-the-background-in-ubuntu-machine

This program uses the binance API to retrieve the latest prices
Binance API URL: https://www.binance.com/restapipub.html

Set shell variables
https://www.digitalocean.com/community/tutorials/how-to-read-and-set-environmental-and-shell-variables-on-a-linux-vps

How to log From Multiple Modules
https://www.blog.pythonlibrary.org/2012/08/02/python-101-an-intro-to-logging/

Configure logging to allow change dynamically
https://docs.python.org/2/howto/logging.html#configuring-logging
'''
import datetime
import httplib
import json
import logging
import os
import smtplib
import socket
import sys
import thread, threading
import time
import urllib2
from collections import deque
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText

# Include the project package into the system path to allow import
package_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, package_path)

# Import your package (if any) below

log = logging.getLogger(__name__)


class API(threading.Thread):
    def __init__(self, url, my_tickers=None, number_of_prices_to_track=30, wait_before_poll=10, percent_limit=30, time_limit=0):
        '''
        param: url
        param: tickers: a list of tickers to monitor
        param: number_of_prices_to_track: total number of prices to keep track for each ticker
        param: wait_before_poll: amount of time (in seconds) to wait before each poll
        param: percent_limit: the percentage change within time_limit before sending out notifications
        param: time_limit: amount of time back (in seconds) to calculate each price percentage change
        '''
        if isinstance(my_tickers, str):
            my_tickers = [my_tickers]

        self.stop = False
        self.url = url
        self.exchange = self.__class__.__name__
        self.my_tickers = my_tickers
        self.number_of_prices_to_track = number_of_prices_to_track
        self.wait_before_poll = wait_before_poll
        self.percent_limit = percent_limit
        self.time_limit = time_limit
        self.verbose = False
        self.config = self.import_config('{}.ini'.format(self.exchange))

        self.tickers_price_history = {}
        self.price_time = {}

        # Get gmail authentication from environmental variables
        # Make sure to set GMAIL and GMAIL_PASS in the .bashrc
        self.gmail = os.environ.get('GMAIL')
        self.gmail_password = os.environ.get('GMAIL_PASS')

        threading.Thread.__init__(self, name=self.exchange)

    def run(self):
        try:
            log.info('Thread {} started...'.format(self.exchange))
            print('Thread {} started...'.format(self.exchange))
            while not self.stop:
                log.debug('Waiting for {}s before next price poll...'.format(self.wait_before_poll))
                time.sleep(self.wait_before_poll)

                # Import config
                self.config = self.import_config('{}.ini'.format(self.exchange))
                log.debug('number of prices: {}, wait before poll: {}s, percent limit: {}%, time limit: {} secs, tickers: {}'.format(self.number_of_prices_to_track, self.wait_before_poll, self.percent_limit, self.time_limit, self.my_tickers))

                # Get new prices
                log.debug('Get price updates')
                try:
                    my_tickers_price_history, my_price_time = self.get_prices(self.my_tickers)
                except (httplib.BadStatusLine, httplib.IncompleteRead, socket.error, urllib2.HTTPError, urllib2.URLError) as e:
                    log.warning('Unable to get price from exchange because of {0}!'.format(e.__class__.__name__))
                    continue  # Skip the rest of the loop below and poll again

                for t, p in my_tickers_price_history.items():
                    # Convert collections.deque to list
                    p = list(p)
                    # log.debug(p)
                    p_time = list(self.price_time[t])
                    # log.debug(p_time)
                    
                    # Go to next item if no price in the ticker
                    if not p:
                        continue

                    # Get min and max price index in each ticker's prices
                    min_price_index = len(p) - 1 - p[::-1].index(min(p))
                    max_price_index = len(p) - 1 - p[::-1].index(max(p))

                    # Assign old and new price
                    old_price = 0
                    new_price = 0
                    old_price_time = None
                    new_price_time = None
                    if min_price_index < max_price_index:
                        old_price = p[min_price_index]
                        old_price_time = p_time[min_price_index]
                        new_price = p[max_price_index]
                        new_price_time = p_time[max_price_index]
                    else:
                        old_price = p[max_price_index]
                        old_price_time = p_time[max_price_index]
                        new_price = p[min_price_index]
                        new_price_time = p_time[min_price_index]

                    # Calculate price fluctuation
                    percent_diff = 0
                    if old_price:
                        percent_diff = (new_price / old_price - 1) * 100
                    # new_price_time = new_price_time.replace(microsecond=0)  # Do not display microsecond
                    # old_price_time = old_price_time.replace(microsecond=0)  # Do not display microsecond
                    time_delta = new_price_time - old_price_time

                    if abs(percent_diff) > self.percent_limit:
                        if not self.time_limit or (time_delta.days == 0 and time_delta.seconds < self.time_limit):
                            # Compose all the messages into email content
                            email_content = self.compose_message(t, percent_diff, old_price, new_price, time_delta, self.config['percent_limit'], self.verbose)
                            log.debug(email_content)
                            if 'email' in self.config.keys():
                                self.send_email(self.config['email'].strip(), '{} Update'.format(self.exchange), email_content)
                                time.sleep(.01)
                            else:
                                log.warning('No email provided in the {}.ini'.format(self.exchange))

                            # Clear the ticker prices to start fresh to prevent script from keep sending message
                            self.tickers_price_history[t].clear()
                            self.price_time[t].clear()

        except Exception as e:
            # Catch all python exceptions occurred in the main thread to log for
            # troubleshooting purposes, since this class is intended to run in
            # the background
            log.error('Exception happened in thread {}!'.format(self.exchange))
            log.exception(e.message)

            # Send Ctrl-C to main thread when exception happens in child thread
            thread.interrupt_main()
        except:
            # Reference: https://stackoverflow.com/questions/18982610/difference-between-except-and-except-exception-as-e-in-python
            log.error('Something nasty happened in thread {}!'.format(self.exchange))

            # Send Ctrl-C to main thread when exception happens in child thread
            thread.interrupt_main()
        finally:
            log.info('Thread {} ended...'.format(self.exchange))
            print('Thread {} ended...'.format(self.exchange))

    def get_prices(self, all_tickers, ticker_key, price_key, my_tickers=None):
        '''Get all prices from URL specified in the class

        param: all_tickers: a list of all the tickers in dictionary form with at least ticker and price key value pair
        param: ticker_key: name used to indicate the ticker field
        param: price_key: name used to indicate the price field
        param: my_tickers: tickers of interest
        '''
        if isinstance(all_tickers, str):
            all_tickers = [all_tickers]
        if isinstance(my_tickers, str):
            my_tickers = [my_tickers]

        if all_tickers:
            for t in all_tickers:
                # Track the prices for all tickers
                # log.debug('{} {}'.format(t[ticker_key], t[price_key]))
                if price_key not in t.keys() or not t[price_key] or t[price_key] == 'N/A':
                    t[price_key] = 0
                if t[ticker_key] in self.tickers_price_history.keys():
                    if not self.tickers_price_history[t[ticker_key]] or not float(t[price_key]) == self.tickers_price_history[t[ticker_key]][-1]:
                        self.tickers_price_history[t[ticker_key]].append(float(t[price_key]))
                        self.price_time[t[ticker_key]].append(datetime.datetime.now())
                else:
                    self.tickers_price_history[t[ticker_key]] = deque([float(t[price_key])], self.number_of_prices_to_track)
                    self.price_time[t[ticker_key]] = deque([datetime.datetime.now()], self.number_of_prices_to_track)

        if my_tickers:
            # Get only tickers that match my_tickers
            my_tickers_price_history = {}
            my_price_time = {}
            for t in my_tickers:
                if t in self.tickers_price_history.keys():
                    my_tickers_price_history[t] = self.tickers_price_history[t]
                    my_price_time[t] = self.price_time[t]
        else:
            my_tickers_price_history = self.tickers_price_history
            my_price_time = self.price_time
        return my_tickers_price_history, my_price_time

    def import_config(self, filename):
        # Import config from .ini
        config = {}

        if os.path.exists(filename):
            with open(filename, 'r') as f:
                for line in f:
                    if not line.strip().startswith('#'):
                        k, v = line.split('=')
                        config[k.strip()] = v.strip()

            # Get percent_limit, default is 30
            if 'percent_limit' in config.keys():
                try:
                    self.percent_limit = float(config['percent_limit'])
                except ValueError:
                    log.warning('Invalid setting, "percent_limit" in {}.ini is not a float!'.format(self.exchange))

            # Get time_limit (in seconds), default is 0 which means no limit
            if 'time_limit' in config.keys():
                try:
                    self.time_limit = int(config['time_limit'])
                except ValueError:
                    log.warning('Invalid setting, "time_limit" in {}.ini is not a integer (in seconds)!'.format(self.exchange))

            # Get logging_level, default is INFO
            if 'logging_level' in config.keys():
                # Set logging level for all loggers
                if config['logging_level'].upper() == 'DEBUG':
                    log.setLevel(logging.DEBUG)
                elif config['logging_level'].upper() == 'INFO':
                    log.setLevel(logging.INFO)
                elif config['logging_level'].upper() == 'WARNING':
                    log.setLevel(logging.WARNING)
                elif config['logging_level'].upper() == 'ERROR':
                    log.setLevel(logging.ERROR)
                elif config['logging_level'].upper() == 'CRITICAL':
                    log.setLevel(logging.CRITICAL)
                else:
                    # Set to default level
                    log.setLevel(logging.INFO)

            # Get my_tickers
            if 'my_tickers' in config.keys():
                if config['my_tickers'] == "":
                    self.my_tickers = None
                else:
                    self.my_tickers = [t.strip() for t in config['my_tickers'].split(',')]

            # Get number_of_prices_to_track
            if 'number_of_prices_to_track' in config.keys():
                try:
                    self.number_of_prices_to_track = int(config['number_of_prices_to_track'])
                except ValueError:
                    log.warning('Invalid setting, "number_of_prices_to_track" in {}.ini is not an integer!'.format(self.exchange))

            # Get wait_before_poll
            if 'wait_before_poll' in config.keys():
                try:
                    self.wait_before_poll = int(config['wait_before_poll'])
                except ValueError:
                    log.warning('Invalid setting, "wait_before_poll" in {}.ini is not an integer!'.format(self.exchange))

            # Get verbosity for email message
            if 'verbose' in config.keys():
                if config['verbose'] == 'True':
                    self.verbose = True
                else:
                    self.verbose = False
        else:
            with open(filename, 'w') as f:
                f.write('email=\n')
                f.write('percent_limit={}\n'.format(self.percent_limit))
                f.write('time_limit={}\n'.format(self.time_limit))
                f.write('logging_level=\n')
                f.write('my_tickers=\n')
                f.write('wait_before_poll={}\n'.format(self.wait_before_poll))
                f.write('verbose=False\n')
        log.debug(config)
        return config

    def compose_message(self, ticker, percent_diff, old_price, new_price, time_delta, percent_limit, verbose=False):
        '''Compose email message.

        Reserved for child class to implement
        '''
        log.info('{0}: {1:+.2f}%, old price: {2:.8f}, new price: {3:.8f}, time_delta: {4}, percent_limit: {5}%'.format(ticker, percent_diff, old_price, new_price, time_delta, percent_limit))
        message = ''
        if verbose:
            message += '==========<br />'
            message += '{} price history information<br />'.format(ticker)
            message += '{}<br />'.format(self.tickers_price_history[ticker])
            message += '{}<br />'.format(self.price_time[ticker])
            for i, price in enumerate(self.tickers_price_history[ticker]):
                message += '{} price is {} on {}<br />'.format(ticker, price, self.price_time[ticker][i])
            message += '==========<br />'
            message += '<br />'
        return message

    def to_hours_minutes_seconds(self, time_delta):
        hours = time_delta.seconds / (60 * 60)
        minutes = time_delta.seconds / 60 % 60
        seconds = time_delta.seconds % 60
        return '{:02d}:{:02d}:{:02d}'.format(hours, minutes, seconds)

    def send_email(self, to, subject, message):
        if not self.gmail or not self.gmail_password:
            log.warning('{} missing "From" email information in environmental variables, skip sending email!'.format(e))
            return
        try:
            # Compose email
            msg = MIMEMultipart()
            msg['From'] = self.gmail
            msg['To'] = to
            msg['Subject'] = subject
            # msg.attach(MIMEText(message, 'plain'))
            msg.attach(MIMEText(message, 'html'))

            # Establish a secure session with gmail's outgoing SMTP server using your gmail account
            # Reference: http://stackabuse.com/how-to-send-emails-with-gmail-using-python/
            #log.info('Establish connection to gmail.')
            smtp_server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            smtp_server.ehlo()

            # Send emails, depends on where it is sending emails from, firewall
            # may cause it to take very long or fail to send emails
            # Reference: https://stackoverflow.com/questions/40998160/python3-smtplib-creating-the-smtp-server-obj-is-very-slow
            #log.info('Login and send email.')
            smtp_server.login(self.gmail, self.gmail_password)
            smtp_server.sendmail(msg['From'], msg['To'], msg.as_string())
            log.info('Sent email to {}.'.format(to))
            
            # Quit SMTP server connection
            smtp_server.quit()
        except Exception as e:
            log.warning('Unexpected error occurred, unable to send email!')
            log.exception(e.message)


class Binance(API):
    def __init__(self, url='https://api.binance.com/api/v1/ticker/allPrices', my_tickers=None, number_of_prices_to_track=30, wait_before_poll=10, percent_limit=30):
        super(Binance, self).__init__(url, my_tickers, number_of_prices_to_track, wait_before_poll, percent_limit)

    def get_prices(self, my_tickers=None):
        '''Get all prices from URL specified in the class

        URL for getting all ticker prices
        Reference: https://stackoverflow.com/questions/17178483/how-do-you-send-an-http-get-web-request-in-python
        '''
        if isinstance(my_tickers, str):
            my_tickers = [my_tickers]

        all_tickers = json.loads(urllib2.urlopen(self.url).read())
        return super(Binance, self).get_prices(all_tickers, 'symbol', 'price', my_tickers=my_tickers)

    def compose_message(self, ticker, percent_diff, old_price, new_price, time_delta, percent_limit, verbose=False):
        '''Compose email message.'''
        message = super(Binance, self).compose_message(ticker, percent_diff, old_price, new_price, time_delta, percent_limit, verbose)

        color = 'green' if percent_diff > 0 else 'red'

        # Only USDT is 4 chars long
        if ticker.endswith('USDT'):
            message += 'https://www.binance.com/trade.html?symbol={}_{}<br />'.format(ticker[:-4], ticker[-4:])
        else:
            message += 'https://www.binance.com/trade.html?symbol={}_{}<br />'.format(ticker[:-3], ticker[-3:])
        message += '{}: <font color="{}">{:+.2f}%</font> in {}<br />'.format(ticker, color, percent_diff, str(time_delta))
        message += 'old price:     {:.8f}<br />'.format(old_price)
        message += 'new price:     {:.8f}<br />'.format(new_price)
        message += 'percent_limit: {}%<br />'.format(percent_limit)
        message += 'Time sent:     {}<br />'.format(datetime.datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'))
        # message += '    '  # Spaces after the message are needed for display purposes when text is received
        message += '<br />'
        return message


class Bittrex(API):
    def __init__(self, url='https://bittrex.com/api/v1.1/public/getmarketsummaries', my_tickers=None, number_of_prices_to_track=30, wait_before_poll=10, percent_limit=30):
        super(Bittrex, self).__init__(url, my_tickers, number_of_prices_to_track, wait_before_poll, percent_limit)

    def get_prices(self, my_tickers=None):
        '''Get all prices from URL specified in the class

        URL for getting all ticker prices
        Reference: https://stackoverflow.com/questions/17178483/how-do-you-send-an-http-get-web-request-in-python

        param: my_tickers
        '''
        if isinstance(my_tickers, str):
            my_tickers = [my_tickers]

        all_tickers = json.loads(urllib2.urlopen(self.url).read())['result']
        return super(Bittrex, self).get_prices(all_tickers, 'MarketName', 'Last', my_tickers=my_tickers)

    def compose_message(self, ticker, percent_diff, old_price, new_price, time_delta, percent_limit, verbose=False):
        '''Compose email message.'''
        message = super(Bittrex, self).compose_message(ticker, percent_diff, old_price, new_price, time_delta, percent_limit, verbose)

        color = 'green' if percent_diff > 0 else 'red'
        message += 'https://www.bittrex.com/Market/Index?MarketName={}<br />'.format(ticker)
        message += '{}: <font color="{}">{:+.2f}%</font> in {}<br />'.format(ticker, color, percent_diff, str(time_delta))
        message += 'old price:     {:.8f}<br />'.format(old_price)
        message += 'new price:     {:.8f}<br />'.format(new_price)
        message += 'percent_limit: {}%<br />'.format(percent_limit)
        message += 'Time sent:     {}<br />'.format(datetime.datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'))
        # message += '    '  # Spaces after the message are needed for display purposes when text is received
        message += '<br />'
        return message


class Idex(API):
    def __init__(self, url='https://api.idex.market/returnTicker', my_tickers=None, number_of_prices_to_track=30, wait_before_poll=10, percent_limit=30):
        super(Idex, self).__init__(url, my_tickers, number_of_prices_to_track, wait_before_poll, percent_limit)

    def get_prices(self, my_tickers=None):
        '''Get all prices from URL specified in the class

        URL for getting all ticker prices
        Reference: https://stackoverflow.com/questions/17178483/how-do-you-send-an-http-get-web-request-in-python

        param: my_tickers
        '''
        if isinstance(my_tickers, str):
            my_tickers = [my_tickers]

        # Reference: https://stackoverflow.com/questions/13303449/urllib2-httperror-http-error-403-forbidden
        req = urllib2.Request(self.url, headers={
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.11 (KHTML, like Gecko) Chrome/23.0.1271.64 Safari/537.11',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.3',
            'Accept-Encoding': 'none',
            'Accept-Language': 'en-US,en;q=0.8',
            'Connection': 'keep-alive'}
        )
        all_tickers = []
        for key, value in json.loads(urllib2.urlopen(req).read()).items():
            value['symbol'] = key
            all_tickers.append(value)
        return super(Idex, self).get_prices(all_tickers, 'symbol', 'last', my_tickers=my_tickers)

    def compose_message(self, ticker, percent_diff, old_price, new_price, time_delta, percent_limit, verbose=False):
        '''Compose email message.'''
        message = super(Idex, self).compose_message(ticker, percent_diff, old_price, new_price, time_delta, percent_limit, verbose)

        color = 'green' if percent_diff > 0 else 'red'
        message += 'https://idex.market/{}<br />'.format(ticker.replace('_', '/'))
        message += '{}: <font color="{}">{:+.2f}%</font> in {}<br />'.format(ticker, color, percent_diff, str(time_delta))
        message += 'old price:     {:.8f}<br />'.format(old_price)
        message += 'new price:     {:.8f}<br />'.format(new_price)
        message += 'percent_limit: {}%<br />'.format(percent_limit)
        message += 'Time sent:     {}<br />'.format(datetime.datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'))
        # message += '    '  # Spaces after the message are needed for display purposes when text is received
        message += '<br />'
        return message


class Kucoin(API):
    def __init__(self, url='https://api.kucoin.com/v1/open/tick', my_tickers=None, number_of_prices_to_track=30, wait_before_poll=10, percent_limit=30):
        super(Kucoin, self).__init__(url, my_tickers, number_of_prices_to_track, wait_before_poll, percent_limit)

    def get_prices(self, my_tickers=None):
        '''Get all prices from URL specified in the class

        URL for getting all ticker prices
        Reference: https://stackoverflow.com/questions/17178483/how-do-you-send-an-http-get-web-request-in-python

        param: my_tickers
        '''
        if isinstance(my_tickers, str):
            my_tickers = [my_tickers]

        all_tickers = json.loads(urllib2.urlopen(self.url).read())['data']
        return super(Kucoin, self).get_prices(all_tickers, 'symbol', 'lastDealPrice', my_tickers=my_tickers)

    def compose_message(self, ticker, percent_diff, old_price, new_price, time_delta, percent_limit, verbose=False):
        '''Compose email message.'''
        message = super(Kucoin, self).compose_message(ticker, percent_diff, old_price, new_price, time_delta, percent_limit, verbose)

        color = 'green' if percent_diff > 0 else 'red'
        message += 'https://www.kucoin.com/#/trade.pro/{}<br />'.format(ticker)
        message += '{}: <font color="{}">{:+.2f}%</font> in {}<br />'.format(ticker, color, percent_diff, str(time_delta))
        message += 'old price:     {:.8f}<br />'.format(old_price)
        message += 'new price:     {:.8f}<br />'.format(new_price)
        message += 'percent_limit: {}%<br />'.format(percent_limit)
        message += 'Time sent:     {}<br />'.format(datetime.datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'))
        # message += '    '  # Spaces after the message are needed for display purposes when text is received
        message += '<br />'
        return message


def main():
    '''Test new code here.  The actual monitor is ran in my_monitor.py'''
    k = Kucoin()
    print(k.get_prices())


if __name__ == '__main__':
    main()

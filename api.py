'''
TODO:  Add to send email in specified time frame, eg. only if price fluctuated 25% within 30 minutes

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
import json
import logging
import os
import smtplib
import sys
import threading
import time
import urllib2
from collections import deque
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText

# Include the project package into the system path to allow import
package_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, package_path)

# Import your package (if any) below
from lib import dec

log = logging.getLogger(__name__)


class API(threading.Thread):
    def __init__(self, url, exchange, my_tickers=None, number_of_prices_to_track=30, wait_before_poll=10, percent_limit=30, time_limit=0):
        '''
        param: url
        param: tickers: a list of tickers to monitor
        param: number_of_prices_to_track: total number of prices to keep track for each ticker
        param: wait_before_poll: amount of time to wait before each poll (in seconds)
        '''
        if isinstance(my_tickers, str):
            my_tickers = [my_tickers]

        self.url = url
        self.exchange = exchange
        self.my_tickers = my_tickers
        self.number_of_prices_to_track = number_of_prices_to_track
        self.wait_before_poll = wait_before_poll
        self.percent_limit = percent_limit
        self.time_limit = time_limit
        self.verbose = False
        self.config = self.import_config('{}.ini'.format(self.exchange))

        self.tickers_price_history = {}
        self.price_time = {}

        threading.Thread.__init__(self, name=self.exchange)

    def run(self):
        try:
            while True:
                log.info('Waiting for {}s before next price poll...'.format(self.wait_before_poll))
                time.sleep(self.wait_before_poll)

                # Import config
                self.config = self.import_config('{}.ini'.format(self.exchange))
                log.info('number of prices: {}, wait before poll: {}s, percent limit: {}%, time limit: {} mins, tickers: {}'.format(self.number_of_prices_to_track, self.wait_before_poll, self.percent_limit, self.time_limit, self.my_tickers))

                # Get new prices
                log.info('Get price updates')
                my_tickers_price_history, my_price_time = self.get_prices(self.my_tickers)

                email_content = ''
                for t, p in my_tickers_price_history.iteritems():
                    # Convert collections.deque to list
                    p = list(p)
                    log.debug(p)
                    p_time = list(self.price_time[t])
                    log.debug(p_time)

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
                    percent_diff = (new_price / old_price - 1) * 100
                    # new_price_time = new_price_time.replace(microsecond=0)  # Do not display microsecond
                    # old_price_time = old_price_time.replace(microsecond=0)  # Do not display microsecond
                    time_diff = new_price_time - old_price_time

                    if abs(percent_diff) > self.percent_limit:
                        if not self.time_limit or (time_diff.days == 0 and time_diff.seconds < self.time_limit):
                            # Compose all the messages into email content
                            email_content += self.compose_message(t, percent_diff, old_price, new_price, time_diff, self.config['percent_limit'], self.verbose)

                            # Clear the ticker prices to start fresh to prevent script from keep sending message
                            self.tickers_price_history[t].clear()
                            self.price_time[t].clear()

                if email_content:
                    log.debug(email_content)
                    if 'email' in self.config.keys():
                        for email in self.config['email'].split(','):
                            self.send_email(email.strip(), '{} Update'.format(self.exchange), email_content)
                            time.sleep(.01)

        except Exception as e:
            # Catch all python exceptions occurred in the main thread to log for
            # troubleshooting purposes, since this class is intended to run in
            # the background
            log.exception(e.message)

    @dec.time_elapsed
    def get_prices(self, all_tickers, ticker_key, price_key, my_tickers=None):
        '''Get all prices from URL specified in the class

        param: ticker_key
        param: price_key
        param: all_tickers: a list of all the tickers in dictionary form with at least ticker and price key value pair
        param: my_tickers: tickers of interest
        '''
        if isinstance(all_tickers, str):
            all_tickers = [all_tickers]
        if isinstance(my_tickers, str):
            my_tickers = [my_tickers]

        for t in all_tickers:
            # Track the prices for all tickers
            # log.debug('{} {}'.format(t[ticker_key], t[price_key]))
            if not t[price_key]:
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

    @dec.time_elapsed
    def import_config(self, filename):
        # Import config from .ini
        config = {}
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

                # Get logging_level, default is WARNING
        if 'logging_level' in config.keys():
            # Set logging level for all loggers
            from lib import all_loggers
            if config['logging_level'].upper() == 'DEBUG':
                all_loggers.setLevelToAllLoggers(logging.DEBUG)
            elif config['logging_level'].upper() == 'INFO':
                all_loggers.setLevelToAllLoggers(logging.INFO)
            elif config['logging_level'].upper() == 'WARNING':
                all_loggers.setLevelToAllLoggers(logging.WARNING)
            elif config['logging_level'].upper() == 'ERROR':
                all_loggers.setLevelToAllLoggers(logging.ERROR)
            elif config['logging_level'].upper() == 'CRITICAL':
                all_loggers.setLevelToAllLoggers(logging.CRITICAL)
            else:
                # Set to default level
                all_loggers.setLevelToAllLoggers(logging.WARNING)

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

        log.debug(config)
        return config

    @dec.time_elapsed
    def compose_message(self, ticker, percent_diff, old_price, new_price, time_diff, percent_limit, verbose=False):
        '''Compose email message.

        Reserved for child class to implement
        '''
        log.info('{0}: {1:+.2f}%, old price: {2:.8f}, new price: {3:.8f}, time_diff: {4}, percent_limit: {5}%'.format(ticker, percent_diff, old_price, new_price, time_diff, percent_limit))
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

    @dec.time_elapsed
    def send_email(self, to, subject, message):
        try:
            # Get gmail authentication from environmental variables
            # Make sure to set GMAIL and GMAIL_PASS in the .bashrc
            email = os.environ['GMAIL']
            password = os.environ['GMAIL_PASS']

            # Compose email
            msg = MIMEMultipart()
            msg['From'] = email
            msg['To'] = to
            msg['Subject'] = subject
            # msg.attach(MIMEText(message, 'plain'))
            msg.attach(MIMEText(message, 'html'))

            # Establish a secure session with gmail's outgoing SMTP server using your gmail account
            # Reference: http://stackabuse.com/how-to-send-emails-with-gmail-using-python/
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(email, password)

            # Send text message through SMS gateway of destination number
            server.sendmail(msg['From'], msg['to'], msg.as_string())

            server.quit()
            log.info('Sent email to {}.'.format(to))
        except KeyError as e:
            log.warning('{} missing in environmental variables, skip sending message!'.format(e))
        except Exception as e:
            log.warning('Unable to send message!')
            log.exception(e.message)


class BinanceAPI(API):
    def __init__(self, url='https://api.binance.com/api/v1/ticker/allPrices', exchange='Binance', my_tickers=None, number_of_prices_to_track=30, wait_before_poll=10, percent_limit=30):
        super(BinanceAPI, self).__init__(url, exchange, my_tickers, number_of_prices_to_track, wait_before_poll, percent_limit)

    @dec.time_elapsed
    def get_prices(self, my_tickers=None):
        '''Get all prices from URL specified in the class

        URL for getting all ticker prices
        Reference: https://stackoverflow.com/questions/17178483/how-do-you-send-an-http-get-web-request-in-python
        '''
        if isinstance(my_tickers, str):
            my_tickers = [my_tickers]
        return super(BinanceAPI, self).get_prices(json.loads(urllib2.urlopen(self.url).read()), 'symbol', 'price', my_tickers=my_tickers)

    @dec.time_elapsed
    def compose_message(self, ticker, percent_diff, old_price, new_price, time_diff, percent_limit, verbose=False):
        '''Compose email message.'''
        message = super(BinanceAPI, self).compose_message(ticker, percent_diff, old_price, new_price, time_diff, percent_limit, verbose)

        color = 'green' if percent_diff > 0 else 'red'

        # Only USDT is 4 chars long
        if ticker.endswith('USDT'):
            message += 'https://www.binance.com/trade.html?symbol={}_{}<br />'.format(ticker[:-4], ticker[-4:])
        else:
            message += 'https://www.binance.com/trade.html?symbol={}_{}<br />'.format(ticker[:-3], ticker[-3:])
        message += '{}: <font color="{}">{:+.2f}%</font> in {}<br />'.format(ticker, color, percent_diff, str(time_diff))
        message += 'old price:     {:.8f}<br />'.format(old_price)
        message += 'new price:     {:.8f}<br />'.format(new_price)
        message += 'percent_limit: {}%<br />'.format(percent_limit)
        message += 'Time sent:     {}<br />'.format(datetime.datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'))
        # message += '    '  # Spaces after the message are needed for display purposes when text is received
        message += '<br />'
        return message


class BittrexAPI(API):
    def __init__(self, url='https://bittrex.com/api/v1.1/public/getmarketsummaries', exchange='Bittrex', my_tickers=None, number_of_prices_to_track=30, wait_before_poll=10, percent_limit=30):
        super(BittrexAPI, self).__init__(url, exchange, my_tickers, number_of_prices_to_track, wait_before_poll, percent_limit)

    @dec.time_elapsed
    def get_prices(self, my_tickers=None):
        '''Get all prices from URL specified in the class

        URL for getting all ticker prices
        Reference: https://stackoverflow.com/questions/17178483/how-do-you-send-an-http-get-web-request-in-python

        param: my_tickers
        '''
        if isinstance(my_tickers, str):
            my_tickers = [my_tickers]
        return super(BittrexAPI, self).get_prices(json.loads(urllib2.urlopen(self.url).read())['result'], 'MarketName', 'Last', my_tickers=my_tickers)

    @dec.time_elapsed
    def compose_message(self, ticker, percent_diff, old_price, new_price, time_diff, percent_limit, verbose=False):
        '''Compose email message.'''
        message = super(BittrexAPI, self).compose_message(ticker, percent_diff, old_price, new_price, time_diff, percent_limit, verbose)

        color = 'green' if percent_diff > 0 else 'red'
        message += 'https://www.bittrex.com/Market/Index?MarketName={}<br />'.format(ticker)
        message += '{}: <font color="{}">{:+.2f}%</font> in {}<br />'.format(ticker, color, percent_diff, str(time_diff))
        message += 'old price:     {:.8f}<br />'.format(old_price)
        message += 'new price:     {:.8f}<br />'.format(new_price)
        message += 'percent_limit: {}%<br />'.format(percent_limit)
        message += 'Time sent:     {}<br />'.format(datetime.datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'))
        # message += '    '  # Spaces after the message are needed for display purposes when text is received
        message += '<br />'
        return message

'''
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


class Monitor(threading.Thread):
    def __init__(self, url, exchange, my_tickers=None, number_of_prices_to_track=30, wait_before_poll=10, inform_limit=50):
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
        self.inform_limit = inform_limit
        self.config = self.import_config('{}.ini'.format(self.exchange))

        self.tickers_price_history = {}

        threading.Thread.__init__(self, name=self.exchange)

    def run(self):
        try:
            while True:
                log.info('Waiting for {}s before next price poll...'.format(self.wait_before_poll))
                time.sleep(self.wait_before_poll)

                # Import config
                self.config = self.import_config('{}.ini'.format(self.exchange))
                log.info(self.my_tickers)
                log.info(self.number_of_prices_to_track)
                log.info(self.wait_before_poll)
                log.info(self.inform_limit)

                # Get new prices
                log.info('Get price updates')
                my_tickers_price_history = self.get_prices(self.my_tickers)

                email_content = ''
                for t, p in my_tickers_price_history.iteritems():
                    # Convert collections.deque to list
                    p = list(p)

                    # Get min and max price index in each ticker's prices
                    min_price_index = len(p) - 1 - p[::-1].index(min(p))
                    max_price_index = len(p) - 1 - p[::-1].index(max(p))

                    # Assign old and new price
                    old_price = 0
                    new_price = 0
                    if min_price_index < max_price_index:
                        old_price = p[min_price_index]
                        new_price = p[max_price_index]
                    else:
                        old_price = p[max_price_index]
                        new_price = p[min_price_index]

                    # Calculate price fluctuation
                    percent_diff = (new_price / old_price - 1) * 100

                    if abs(percent_diff) > self.inform_limit:
                        # Compose all the messages into email content
                        email_content += self.compose_message(t, percent_diff, old_price, new_price, self.config['inform_limit'])

                        # Clear the ticker prices to start fresh to prevent script from keep sending message
                        self.tickers_price_history[t].clear()

                if email_content:
                    log.debug(email_content)
                    if 'email' in self.config.keys():
                        for email in self.config['email'].split(','):
                            self.send_email(email.strip(), '{} Update'.format(self.exchange), email_content)
                            time.sleep(.01)

        except Exception as e:
            # Catch all python exceptions occurred in the main thread to log for
            # troubleshooting purposes, since this monitor is intended to run in
            # the background
            log.exception(e.message)

    @dec.time_elapsed
    def get_prices(self, my_tickers=None):
        pass

    @dec.time_elapsed
    def import_config(self, filename):
        # Import config from .ini
        config = {}
        with open(filename, 'r') as f:
            for line in f:
                if not line.strip().startswith('#'):
                    k, v = line.split('=')
                    config[k.strip()] = v.strip()

        # Get inform_limit, default is 50
        if 'inform_limit' in config.keys():
            try:
                self.inform_limit = float(config['inform_limit'])
            except ValueError:
                log.warning('Invalid setting, "inform_limit" in {}.ini is not a float!'.format(self.exchange))

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

        log.debug(config)
        return config

    @dec.time_elapsed
    def compose_message(self, ticker, percent_diff, old_price, new_price, inform_limit):
        '''Compose email message.

        Reserved for child class to implement
        '''
        log.info('{0}: {1:+.2f}%, old price: {2:.8f}, new price: {3:.8f}, inform_limit: {4}%'.format(ticker, percent_diff, old_price, new_price, inform_limit))
        return ''

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


class BinanceMonitor(Monitor):
    def __init__(self, url='https://api.binance.com/api/v1/ticker/allPrices', exchange='Binance', my_tickers=None, number_of_prices_to_track=30, wait_before_poll=10, inform_limit=50):
        super(BinanceMonitor, self).__init__(url, exchange, my_tickers, number_of_prices_to_track, wait_before_poll, inform_limit)

    @dec.time_elapsed
    def get_prices(self, my_tickers=None):
        '''Get all prices from URL specified in the class

        URL for getting all ticker prices
        Reference: https://stackoverflow.com/questions/17178483/how-do-you-send-an-http-get-web-request-in-python
        '''
        if isinstance(my_tickers, str):
            my_tickers = [my_tickers]
        all_tickers = json.loads(urllib2.urlopen(self.url).read())
        for t in all_tickers:
            # Track the prices for all tickers
            log.debug('{} {}'.format(t['symbol'], t['price']))
            if not t['price']:
                t['price'] = 0
            if t['symbol'] in self.tickers_price_history.keys():
                self.tickers_price_history[t['symbol']].append(float(t['price']))
            else:
                self.tickers_price_history[t['symbol']] = deque([float(t['price'])], self.number_of_prices_to_track)

        if my_tickers:
            # Get only tickers that match my_tickers
            my_tickers_price_history = {}
            for t in my_tickers:
                if t in self.tickers_price_history.keys():
                    my_tickers_price_history[t] = self.tickers_price_history[t]
        else:
            my_tickers_price_history = self.tickers_price_history
        return my_tickers_price_history

    @dec.time_elapsed
    def compose_message(self, ticker, percent_diff, old_price, new_price, inform_limit):
        '''Compose email message.'''
        message = super(BinanceMonitor, self).compose_message(ticker, percent_diff, old_price, new_price, inform_limit)

        color = 'green' if percent_diff > 0 else 'red'

        # Only USDT is 4 chars long
        if ticker.endswith('USDT'):
            message += 'https://www.binance.com/trade.html?symbol={}_{}<br />'.format(ticker[:-4], ticker[-4:])
        else:
            message += 'https://www.binance.com/trade.html?symbol={}_{}<br />'.format(ticker[:-3], ticker[-3:])
        message +=  '{}: <font color="{}">{:+.2f}%</font><br />'.format(ticker, color, percent_diff)
        message += 'old price: {:.8f}<br />'.format(old_price)
        message += 'new price: {:.8f}<br />'.format(new_price)
        message += 'inform_limit: {}%<br />'.format(inform_limit)
        message += 'Time sent: {}<br />'.format(datetime.datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'))
        # message += '    '  # Spaces after the message are needed for display purposes when text is received
        message += '<br />'
        return message


class BittrexMonitor(Monitor):
    def __init__(self, url='https://bittrex.com/api/v1.1/public/getmarketsummaries', exchange='Bittrex', my_tickers=None, number_of_prices_to_track=30, wait_before_poll=10, inform_limit=50):
        super(BittrexMonitor, self).__init__(url, exchange, my_tickers, number_of_prices_to_track, wait_before_poll, inform_limit)

    @dec.time_elapsed
    def get_prices(self, my_tickers=None):
        '''Get all prices from URL specified in the class

        URL for getting all ticker prices
        Reference: https://stackoverflow.com/questions/17178483/how-do-you-send-an-http-get-web-request-in-python
        '''
        if isinstance(my_tickers, str):
            my_tickers = [my_tickers]
        all_tickers = json.loads(urllib2.urlopen(self.url).read())['result']
        for t in all_tickers:
            # Track the prices for all tickers
            log.debug('{} {}'.format(t['MarketName'], t['Last']))
            if not t['Last']:
                t['Last'] = 0
            if t['MarketName'] in self.tickers_price_history.keys():
                self.tickers_price_history[t['MarketName']].append(float(t['Last']))
            else:
                self.tickers_price_history[t['MarketName']] = deque([float(t['Last'])], self.number_of_prices_to_track)

        if my_tickers:
            # Get only tickers that match my_tickers
            my_tickers_price_history = {}
            for t in my_tickers:
                if t in self.tickers_price_history.keys():
                    my_tickers_price_history[t] = self.tickers_price_history[t]
        else:
            my_tickers_price_history = self.tickers_price_history
        return my_tickers_price_history

    @dec.time_elapsed
    def compose_message(self, ticker, percent_diff, old_price, new_price, inform_limit):
        '''Compose email message.'''
        message = super(BittrexMonitor, self).compose_message(ticker, percent_diff, old_price, new_price, inform_limit)

        color = 'green' if percent_diff > 0 else 'red'
        message += 'https://www.bittrex.com/Market/Index?MarketName={}<br />'.format(ticker)
        message +=  '{}: <font color="{}">{:+.2f}%</font><br />'.format(ticker, color, percent_diff)
        message += 'old price: {:.8f}<br />'.format(old_price)
        message += 'new price: {:.8f}<br />'.format(new_price)
        message += 'inform_limit: {}%<br />'.format(inform_limit)
        message += 'Time sent: {}<br />'.format(datetime.datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'))
        # message += '    '  # Spaces after the message are needed for display purposes when text is received
        message += '<br />'
        return message

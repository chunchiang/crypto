#!/usr/bin/python
'''
The program is running in the background
Reference: https://askubuntu.com/questions/396654/how-to-run-the-python-program-in-the-background-in-ubuntu-machine

This program uses the binance API to retrieve the latest prices
Binance API URL: https://www.binance.com/restapipub.html

Set shell variables
https://www.digitalocean.com/community/tutorials/how-to-read-and-set-environmental-and-shell-variables-on-a-linux-vps

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


# Initialize log
file = os.path.basename(__file__).split('.')[0]
file_name = '{}/logs/{}_{}.log'.format(os.path.dirname(os.path.realpath(__file__)), datetime.datetime.now().isoformat().replace(':', '').replace('-', '').replace('.', ''), file)
log = logging.getLogger(file)
handler = logging.FileHandler(file_name)
formatter = logging.Formatter('%(asctime)s %(name)-8s %(threadName)-10s %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
log.addHandler(handler)


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
                log.debug(self.my_tickers)
                log.debug(self.number_of_prices_to_track)
                log.debug(self.wait_before_poll)
                log.debug(self.inform_limit)

                # Get new prices
                my_tickers_price_history = self.get_prices(self.my_tickers)
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
                    price_diff = new_price - old_price
                    percent_diff = (new_price / old_price - 1) * 100
                    message = '{0}: {1:+.2f}%, old price: {2:.8f}, new price: {3:.8f}, inform_limit: {4}%'.format(t, percent_diff, old_price, new_price, self.config['inform_limit'])
                    log.info(message)

                    if abs(percent_diff) > self.config['inform_limit']:
                        if 'email' in self.config.keys():
                            for email in self.config['email'].split(','):
                                self.send_email(email.strip(), '{} Update'.format(self.exchange), compose_message(message, t))

                        # Clear the ticker prices to start fresh to prevent script from keep sending message
                        self.tickers_price_history[t].clear()
                        time.sleep(.01)
        except Exception as e:
            # Catch all python exceptions occurred in the main thread to log for
            # troubleshooting purposes, since this monitor is intended to run in
            # the background
            log.exception(e.message)

    #@print_function_name
    def get_prices(self, my_tickers=None):
        pass

    #@print_function_name
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
            except ValueError as e:
                log.warning('Invalid setting, "inform_limit" in {}.ini is not a float!'.format(self.exchange))
        
        # Get logging_level, default is WARNING
        if 'logging_level' in config.keys():
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
                log.setLevel(logging.WARNING)
        else:
            # Set to default level
            log.setLevel(logging.WARNING)
            
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
            except ValueError as e:
                log.warning('Invalid setting, "number_of_prices_to_track" in {}.ini is not an integer!'.format(self.exchange))
            
        # Get wait_before_poll
        if 'wait_before_poll' in config.keys():
            try:
                self.wait_before_poll = int(config['wait_before_poll'])
            except ValueError as e:
                log.warning('Invalid setting, "wait_before_poll" in {}.ini is not an integer!'.format(self.exchange))

        log.debug(config)
        return config
        
    def compose_message(self, original_message, ticker):
        pass
        
    #@print_function_name
    def send_email(self, to, subject, message):
        try:
            # Gmail authentication
            email = os.environ['GMAIL']
            password = os.environ['GMAIL_PASS']

            # Compose email
            msg = MIMEMultipart()
            msg['From'] = email
            msg['To'] = to
            msg['Subject'] = subject
            msg.attach(MIMEText(message, 'plain'))

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
            log.info('Sent email to {}.'.format(email))
        except KeyError as e:
            log.warning('{} missing in environmental variables, skip sending message!'.format(e))
        except:
            log.warning('Unable to send message!')


class BinanceMonitor(Monitor):
    def __init__(self, url, exchange='Binance', my_tickers=None, number_of_prices_to_track=30, wait_before_poll=10, inform_limit=50):
        super(BinanceMonitor, self).__init__(url, exchange, my_tickers, number_of_prices_to_track, wait_before_poll, inform_limit)

    #@print_function_name
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
            if t['symbol'] in self.tickers_price_history.keys():
                self.tickers_price_history[t['symbol']].append(float(t['price']))
            else:
                self.tickers_price_history[t['symbol']] = deque([float(t['price'])], self.number_of_prices_to_track)

        log.debug(my_tickers)
        if my_tickers:
            # Get only tickers that match my_tickers
            my_tickers_price_history = {}
            for t in my_tickers:
                if t in self.tickers_price_history.keys():
                    my_tickers_price_history[t] = self.tickers_price_history[t]
        else:
            my_tickers_price_history = self.tickers_price_history
        log.debug(my_tickers_price_history)
        return my_tickers_price_history
        
    #@print_function_name
    def compose_message(self, original_message, ticker):
        # Compose message
        message = original_message.replace(', ', '\n') + '\n'
        # Only USDT is 4 chars long
        if ticker.endswith('USDT'):
            message += 'https://www.binance.com/trade.html?symbol={}_{}\n'.format(t[:-4], t[-4:])
        else:
            message += 'https://www.binance.com/trade.html?symbol={}_{}\n'.format(t[:-3], t[-3:])
        message += 'Time sent: {}\n'.format(datetime.datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'))
        # message += '    '  # Spaces after the message are needed for display purposes when text is received
        return message
        

class BittrexMonitor(Monitor):
    def __init__(self, url, exchange='Bittrex', my_tickers=None, number_of_prices_to_track=30, wait_before_poll=10, inform_limit=50):
        super(BittrexMonitor, self).__init__(url, exchange, my_tickers, number_of_prices_to_track, wait_before_poll, inform_limit)
        
    #@print_function_name
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
            if t['MarketName'] in self.tickers_price_history.keys():
                self.tickers_price_history[t['MarketName']].append(float(t['Last']))
            else:
                self.tickers_price_history[t['MarketName']] = deque([float(t['Last'])], self.number_of_prices_to_track)

        log.debug(my_tickers)
        if my_tickers:
            # Get only tickers that match my_tickers
            my_tickers_price_history = {}
            for t in my_tickers:
                if t in self.tickers_price_history.keys():
                    my_tickers_price_history[t] = self.tickers_price_history[t]
        else:
            my_tickers_price_history = self.tickers_price_history
        log.debug(my_tickers_price_history)
        return my_tickers_price_history

    #@print_function_name
    def compose_message(self, original_message, ticker):
        # Compose message
        message = original_message.replace(', ', '\n') + '\n'
        message += 'https://www.bittrex.com/Market/Index?MarketName=BTC-ETH={}\n'.format(ticker)
        message += 'Time sent: {}\n'.format(datetime.datetime.now().strftime('%Y-%m-%d %I:%M:%S %p'))
        # message += '    '  # Spaces after the message are needed for display purposes when text is received
        return message


if __name__ == '__main__':
    try:
        binance_url = 'https://api.binance.com/api/v1/ticker/allPrices'
        bittrex_url = 'https://bittrex.com/api/v1.1/public/getmarketsummaries'

        binance = BinanceMonitor(binance_url, number_of_prices_to_track=180)
        bittrex = BittrexMonitor(bittrex_url, number_of_prices_to_track=180)

        binance.start()
        bittrex.start()
    except Exception as e:
        # Catch all python exceptions occurred in the main thread to log for
        # troubleshooting purposes, since this monitor is intended to run in
        # the background
        log.exception(e.message)

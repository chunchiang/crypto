#!/usr/bin/python
'''my_monitor.py for monitoring binance and bittrex price fluctuations.

Usage:
    ./my_monitor.py &

Stop the program:
    $ ps -e | grep monitor
     1828 pts/8    00:00:00 my_monitor.py
    $ kill -9 1828

'''
import datetime
import logging
import logging.config
import os
import sys

# Include the project package into the system path to allow import
package_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, package_path)

# Import your package (if any) below
import api
from lib import all_loggers

# Create log directory to store all logs for current UUT
log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir, 0755)  # Equivalent to mkdir -p

# Initialize loggers
this_filename = os.path.basename(__file__).split('.')[0]
# filename = '~/{0}/{1}/{1}_{2}.log'.format(log_dir, this_filename, datetime.datetime.now().isoformat().replace(':', '').replace('-', '').replace('.', ''))
filename = '{}/{}_{}.log'.format(log_dir, this_filename, datetime.datetime.now().isoformat().replace(':', '').replace('-', '').replace('.', ''))
handler = logging.FileHandler(filename)
formatter = logging.Formatter('%(asctime)s %(name)-8s %(threadName)-10s %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
log = logging.getLogger(__name__)
all_loggers.addHandlerToAllLoggers(handler)
all_loggers.setLevelToAllLoggers(logging.INFO)
log.info('Logging started...')

if __name__ == '__main__':
    try:
        binance = api.Binance(number_of_prices_to_track=300)
        binance.start()

        bittrex = api.Bittrex(number_of_prices_to_track=300)
        bittrex.start()
    except Exception as e:
        # Catch all python exceptions occurred in the main thread to log for
        # troubleshooting purposes, since this monitor is intended to run in
        # the background
        log.error('Something nasty happened in my_monitor!')
        log.exception(e.message)

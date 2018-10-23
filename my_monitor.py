#!/usr/bin/python
'''This program monitors crypto exchanges price fluctuation.

Usage:
    Running in terminal session (must keep the session open, if session is closed, the program stops)
    $ ./my_monitor.py

    Running in the backgound
    Reference: https://stackoverflow.com/questions/2975624/how-to-run-a-python-script-in-the-background-even-after-i-logout-ssh
    $ nohup ./my_monitor.py &

    Stop the program:
    $ ps -e | grep monitor
     1828 pts/8    00:00:00 my_monitor.py
    $ kill -9 1828

TODO: Add to start/stop thread without having to start/stop my_monitor.
TODO: Figure out why it takes so long (> 2 mins) for email to be sent.
'''
import datetime
import logging
import logging.config
import os
import sys
import threading

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


def main():
    try:
        log.info('{0} started as PID {1}...'.format(this_filename, os.getpid()))
        threads = []
        threads.append(api.Binance(number_of_prices_to_track=300))
        threads.append(api.Bittrex(number_of_prices_to_track=300))
        threads.append(api.Idex(number_of_prices_to_track=300))
        threads.append(api.Kucoin(number_of_prices_to_track=300))

        # Start all threads
        for t in threads:
            t.start()

        # Monitor child threads in case exceptions happen
        old_time = datetime.datetime.now()
        while True:
            # Display the threads that are still running every 10 minutes
            new_time = datetime.datetime.now()
            time_delta = new_time - old_time
            if time_delta.seconds > 600:
                running_threads = ''
                for t in threads:
                    if t.is_alive():
                        if running_threads:
                            running_threads += ', '
                        running_threads += t.exchange
                log.info('{0} still running...'.format(running_threads))
                # log.info('Still running...')
                old_time = new_time
    except KeyboardInterrupt:
        # Reference: https://helpful.knobs-dials.com/index.php/Python_notes_-_threads/threading#Timely_thread_cleanup.2C_and_getting_Ctrl-C_to_work
        log.warning('Ctrl-C entered.')
        print('Ctrl-C entered.')
    except Exception as e:
        # Catch all python exceptions occurred in the main thread to log for
        # troubleshooting purposes, since this monitor is intended to run in
        # the background
        log.error('Exception happened in my_monitor!')
        log.exception(e.message)
    except:
        # Reference: https://stackoverflow.com/questions/18982610/difference-between-except-and-except-exception-as-e-in-python
        log.error('Something nasty happened in my_monitor!')
    finally:
        log.info('Stopping all threads!')
        print('Stopping all threads!')

        # Stop and wait for threads to finish
        for t in threads:
            t.stop = True
            t.join()
        log.info('{0} ended...'.format(this_filename))


if __name__ == '__main__':
    main()

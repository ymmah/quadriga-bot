from __future__ import unicode_literals

import io
import os
import json
import time
import datetime
import logging
import smtplib
import multiprocessing

import pytz
import quadriga

# Set up the logger
logger = logging.getLogger('quadriga-bot')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    fmt='[%(asctime)s][%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler = logging.FileHandler('quadriga-bot.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

DEFAULT_CONFIG = {
    # The order book to poll
    'order_book': 'eth_cad',
    # QuadrigaCX URL path for the link in the message
    'url_path': '/trade/eth/cad',
    # Price delta threshold to send emails on
    'max_delta': 2,
    # Number of seconds to sleep after each poll
    'sleep': 10,
    # Sender (bot) email address
    'sender_email': None,
    # Sender (bot) email password
    'sender_password': None,
    # Recipient email addresses
    'to_emails': None,
    # Timezone to use for datetime
    'timezone': 'Canada/Pacific',
    # Timeout for each request
    'timeout': 10,
    # Number of seconds to wait before sending out an email anyway
    'max_idle': 3600 * 12
}
# Load the bot configuration from ~/.quadriga-bot
config = DEFAULT_CONFIG.copy()
with io.open(os.path.expanduser('~/.quadriga-bot'), mode='rt') as fp:
    config.update(json.load(fp))

for setting in DEFAULT_CONFIG.keys():
    if config.get(setting) is None:
        raise ValueError('Config file is missing key "{}"'.format(setting))

quadriga_client = quadriga.QuadrigaClient(default_book=config['order_book'])

sender_email = config['sender_email']
sender_pass = config['sender_password']
to_emails = config['to_emails']
timeout = int(config['timeout'])
sleep = int(config['sleep'])
max_idle = int(config['max_idle'])
max_delta = int(config['max_delta'])
url = 'https://www.quadrigacx.com' + config['url_path']
tz = pytz.timezone(config['timezone'])
coin = 'Ether' if 'eth' in config['order_book'] else 'Bitcoin'


def get_price():
    summary = quadriga_client.get_summary()
    return float(summary['last'])


def send_email(subject, message):
    header = '\n'.join([
        'From: {}'.format(sender_email),
        'To: {}'.format(','.join(to_emails)),
        'Subject: {}\n'.format(subject)
    ])
    server = smtplib.SMTP('smtp.gmail.com:587')
    server.ehlo()
    server.starttls()
    server.login(sender_email, sender_pass)
    server.sendmail(sender_email, to_emails, header + message)
    server.quit()


def entry_point():
    logger.info('Starting QuadrigaCX bot ...')
    pool = multiprocessing.Pool(processes=1)
    last_price = pool.apply_async(get_price).get(timeout)
    last_time = datetime.datetime.now()

    while True:
        time.sleep(sleep)
        try:
            cur_price = pool.apply_async(get_price).get(timeout)
        except multiprocessing.TimeoutError:
            logger.warn('Timeout while polling QuadrigaCX')
        except Exception as err:
            logger.warn('Failed to poll QuadrigaCX: {}'.format(err))
        else:
            logger.debug('Last trade at ${}'.format(cur_price))

            cur_time = datetime.datetime.now()
            delta = abs(last_price - cur_price)
            idle = (cur_time - last_time).total_seconds()

            if (idle >= max_idle and delta) or (delta >= max_delta):
                logger.info('Sending emails to {} ...'.format(to_emails))
                trend = 'down' if last_price > cur_price else 'up'
                since = tz.localize(last_time).strftime('%Y-%m-%d %I:%M %p')
                send_email(
                    subject='{} went {} to ${}!'.format(coin, trend, cur_price),
                    message='{} went {} to ${} since {}.\n\n'.format(
                        coin, trend, cur_price, since
                    ) + 'For more information visit: {}.'.format(url)
                )
                last_price, last_time = cur_price, cur_time

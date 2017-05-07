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
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

default_config = {
    # The order book to poll
    'order_book': 'eth_cad',
    # QuadrigaCX URL path for the link in the message
    'url_path': '/trade/eth/cad',
    # Price delta threshold to send emails on
    'max_delta': 2,
    # Number of seconds to sleep after each poll
    'sleep': 5,
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
    'max_idle': 3600 * 12,
    # Number of polls before a new process is spawned
    'process_ttl': 10000
}
order_books = {'btc_cad', 'btc_usd', 'eth_cad', 'eth_usd'}
coins = {'eth': 'Ether', 'btc': 'Bitcoin'}
client = quadriga.QuadrigaClient()


def load_config():
    config = default_config.copy()
    with io.open(os.path.expanduser('~/.quadriga-bot'), mode='rt') as fp:
        config.update(json.load(fp))

    for key in default_config.keys():
        if config.get(key) is None:
            raise ValueError('missing config key "{}"'.format(key))

    if config['order_book'] not in order_books:
        raise ValueError('invalid order book "{}"'.format(config['order_book']))
    if '@gmail.com' not in config['sender_email']:
        raise ValueError('only @gmail.com is supported for bot email')
    if not isinstance(config['to_emails'], list):
        raise ValueError('"to_emails" not a list of email addresses')

    for key in ['max_idle', 'max_delta', 'sleep', 'timeout', 'process_ttl']:
        try:
            config[key] = int(config[key])
        except (TypeError, ValueError):
            raise ValueError(
                'config key "{}" has a non-numeric value: {}'
                .format(key, config[key])
            )
    try:
        pytz.timezone(config['timezone'])
    except pytz.exceptions.UnknownTimeZoneError:
        raise ValueError('invalid timezone "{}"'.format(config['timezone']))
    return config


def get_price(order_book):
    summary = client.get_summary(order_book)
    return float(summary['ask'])


def send_email(sender_email, sender_pass, to_emails, subject, message):
    logger.debug('Alerting {} ...'.format(to_emails))
    try:
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
    except Exception as err:
        logger.exception('Failed to send alerts: {}'.format(err))


def entry_point():
    logger.debug('Starting QuadrigaCX price checker ...')
    pool = multiprocessing.Pool(processes=1)
    last_price = get_price(load_config()['order_book'])
    last_time = datetime.datetime.now()
    iterations = 0

    while True:
        try:
            config = load_config()
        except Exception as err:
            logger.exception('Failed to load config: {}'.format(err))
            time.sleep(default_config['sleep'])
            continue
        if iterations > config['process_ttl']:
            try:
                pool.terminate()
            except Exception as err:
                logger.exception('Failed to terminate process: {}'.format(err))
            finally:
                pool = multiprocessing.Pool(processes=1)
                iterations = 0
        try:
            process_task = pool.apply_async(get_price, [config['order_book']])
            cur_price = process_task.get(int(config['timeout']))
        except multiprocessing.TimeoutError:
            logger.exception('Timeout while polling QuadrigaCX')
        except Exception as err:
            logger.exception('Failed to poll QuadrigaCX: {}'.format(err))
        else:
            major, minor = config['order_book'].lower().split('_')
            major, minor = coins[major], minor.upper()

            cur_time = datetime.datetime.now()
            delta = abs(last_price - cur_price)
            idle = (cur_time - last_time).total_seconds()

            logger.debug('Last sell price for {}: ${:,.2f} {}'.format(
                major.lower(), cur_price, minor
            ))
            if ((idle >= config['max_idle']) and delta) or \
                    (delta >= config['max_delta']):

                trend = 'down' if last_price > cur_price else 'up'
                tz = pytz.timezone(config['timezone'])
                since = tz.localize(last_time).strftime('%Y-%m-%d %I:%M %p')
                send_email(
                    sender_email=config['sender_email'],
                    sender_pass=config['sender_password'],
                    to_emails=config['to_emails'],
                    subject='{} went {} to ${:,.2f} {}!'.format(
                        major, trend, cur_price, minor
                    ),
                    message='{} went {} to ${:,.2f} {} since {}.\n\n'.format(
                        major, trend, cur_price, minor, since
                    ) + 'For more information visit: {}'.format(
                        'https://www.quadrigacx.com' + config['url_path']
                    )
                )
                last_price, last_time = cur_price, cur_time

            time.sleep(int(config['sleep']))
            iterations += 1

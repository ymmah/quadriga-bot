from __future__ import unicode_literals

import io
import os
import sys
import json
import time
import datetime
import logging
import smtplib

import pytz
import quadriga


QUADRIGACX_URL = 'https://www.quadrigacx.com'
DEFAULT_CONFIG_PATH = '~/.quadriga-bot'
DEFAULT_CONFIG_SETTINGS = {
    # The order book to poll
    'order_book': 'eth_cad',
    # QuadrigaCX URL path for the link in the message
    'url_path': '/trade/eth/cad',
    # Price delta to send emails on
    'price_delta': 2,
    # Number of seconds to sleep after each poll
    'poll_wait': 10,
    # Sender (bot) email address
    'sender_email': None,
    # Sender (bot) email password
    'sender_password': None,
    # Recipient email addresses
    'to_emails': None,
    # Timezone to use for datetime
    'timezone': 'Canada/Pacific'
}

logger = logging.getLogger('quadriga-bot')
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    fmt='[%(asctime)s][%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler = logging.FileHandler('quadriga-bot.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(stream_handler)


def abort_program(message, error_code=1):
    logger.error(message)
    sys.exit(error_code)


def entry_point():
    logger.info('Starting QuadrigaCX bot ...')
    config = DEFAULT_CONFIG_SETTINGS
    config_path = os.path.abspath(os.path.expanduser(DEFAULT_CONFIG_PATH))
    try:
        with io.open(config_path, mode='rt') as config_file:
            config.update(json.load(config_file))
    except (IOError, OSError, ValueError):
        abort_program('Missing or bad config file "{}"'.format(config_path))

    for setting in DEFAULT_CONFIG_SETTINGS.keys():
        if config[setting] is None:
            abort_program('Config file missing key "{}"'.format(setting))

    currency = 'Ether' if 'eth' in config['order_book'] else 'Bitcoin'
    tz = pytz.timezone(config['timezone'])

    client = quadriga.QuadrigaClient(default_book=config['order_book'])
    summary = client.get_summary()
    last_price = float(summary['last'])
    last_time = datetime.datetime.now()

    while True:
        try:
            summary = client.get_summary()
            cur_price = float(summary['last'])
            cur_time = datetime.datetime.now()
            logger.info('Last trade at {}'.format(cur_price))
        except Exception as err:
            logger.warn('Failed to get summary: {}'.format(err))
        else:
            if abs(last_price - cur_price) >= config['price_delta']:
                direction = 'down' if last_price > cur_price else 'up'
                logger.info(
                    'Significant price change detected. '
                    'Sending emails to {} ...'.format(config['to_emails'])
                )
                email_subject = '{} went {} to ${}!'.format(
                    currency, direction, cur_price
                )
                email_message = '{} went {} to ${} since {}.\n\n'.format(
                    currency,
                    direction,
                    cur_price,
                    tz.localize(last_time).strftime('%Y-%m-%d %I:%M %p')
                )
                email_message += 'For more information visit: {}.'.format(
                    QUADRIGACX_URL + config['url_path']
                )
                try:
                    send_email(
                        config['sender_email'],
                        config['sender_password'],
                        config['to_emails'],
                        email_subject,
                        email_message,
                    )
                except Exception as err:
                    logger.exception('Failed to send email(s): {}'.format(err))
                last_price = cur_price
                last_time = cur_time

        time.sleep(config['poll_wait'])


def send_email(sender_email, sender_password, to_emails, subject, message):
    header = '\n'.join([
        'From: {}'.format(sender_email),
        'To: {}'.format(','.join(to_emails)),
        'Subject: {}\n'.format(subject)
    ])
    server = smtplib.SMTP('smtp.gmail.com:587')
    server.ehlo()
    server.starttls()
    server.login(sender_email, sender_password)
    result = server.sendmail(sender_email, to_emails, header + message)
    server.quit()
    return result

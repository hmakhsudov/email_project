import os
import ssl
import poplib
from email import parser
from email.header import decode_header
from django.conf import settings
import logging
import requests
import pandas as pd
from .models import Order
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime


logger = logging.getLogger(__name__)

def fetch_emails():
    EMAIL_HOST = settings.EMAIL_HOST
    EMAIL_PORT = settings.EMAIL_PORT
    EMAIL_USER = settings.EMAIL_USER
    EMAIL_PASSWORD = settings.EMAIL_PASSWORD

    UIDL_FILE = os.path.join(settings.BASE_DIR, 'processed_uidls.txt')

    if os.path.exists(UIDL_FILE):
        with open(UIDL_FILE, 'r') as f:
            processed_uidls = set(f.read().splitlines())
    else:
        processed_uidls = set()

    context = ssl.create_default_context()
    pop_conn = poplib.POP3_SSL(EMAIL_HOST, EMAIL_PORT, context=context)
    pop_conn.user(EMAIL_USER)
    pop_conn.pass_(EMAIL_PASSWORD)

    response, listings, octets = pop_conn.uidl()
    messages = []
    new_uidls = []

    allowed_senders = ['bnmagnats@gmail.com',]  

    for listing in reversed(listings):
        number, uidl = listing.decode().split(' ')

        if uidl in processed_uidls:
            continue

        response, lines, octets = pop_conn.top(int(number), 0)
        raw_email = b"\n".join(lines)
        email_message = parser.BytesParser().parsebytes(raw_email)

        from_email = email_message.get('From', '')
        from_email = decode_email_address(from_email)

        if from_email not in allowed_senders:
            continue

        response, lines, octets = pop_conn.retr(int(number))
        raw_email = b"\n".join(lines)
        email_message = parser.BytesParser().parsebytes(raw_email)

        messages.append((email_message, uidl))
        new_uidls.append(uidl)

    pop_conn.quit()

    return messages, new_uidls

def process_email_attachments(messages_with_uidls):
    processed_uidls = []
    for message, uidl in messages_with_uidls:
        date_header = message['Date']
        if date_header is None:
            logger.warning('Заголовок Date отсутствует в письме. Пропускаем сообщение.')
            continue

        try:
            date_tuple = parsedate_to_datetime(date_header)
        except Exception as e:
            logger.warning(f'Не удалось разобрать дату письма: {e}. Пропускаем сообщение.')
            continue

        if date_tuple.tzinfo is None:
            date_threshold = datetime.now() - timedelta(days=30)
        else:
            date_threshold = datetime.now(date_tuple.tzinfo) - timedelta(days=30)

        if date_tuple < date_threshold:
            logger.info('Письмо слишком старое. Пропускаем.')
            continue  
        from_email = message.get('From')
        subject = get_decoded_subject(message)

        logger.info(f'Обрабатываем письмо от: {from_email}, Тема: {subject}')

        for part in message.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue
            file_name = part.get_filename()
            if file_name:
                file_name = decode_filename(file_name)
                if file_name.endswith('.xlsx') or file_name.endswith('.xls'):
                    file_path = save_attachment(part, file_name)
                    logger.info(f'Saved attachment to: {file_path}')
                    parse_excel_file(file_path)
                    os.remove(file_path)
                    logger.info(f'Deleted temporary file: {file_path}')
                else:
                    logger.warning(f'Attachment {file_name} is not an Excel file.')
        processed_uidls.append(uidl)

    if processed_uidls:
        UIDL_FILE = os.path.join(settings.BASE_DIR, 'processed_uidls.txt')
        with open(UIDL_FILE, 'a') as f:
            for uidl in processed_uidls:
                f.write(uidl + '\n')

def decode_email_address(address):
    from email.header import decode_header
    import re
    decoded_fragments = decode_header(address)
    address_parts = []
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            encoding = encoding or 'utf-8'
            fragment = fragment.decode(encoding, errors='ignore')
        address_parts.append(fragment)
    full_address = ''.join(address_parts)
    match = re.search(r'<(.+?)>', full_address)
    if match:
        return match.group(1).strip()
    else:
        return full_address.strip()

def get_decoded_subject(message):
    subject = message.get('Subject', '')
    decoded_fragments = decode_header(subject)
    subject_parts = []
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            encoding = encoding or 'utf-8'
            fragment = fragment.decode(encoding, errors='ignore')
        subject_parts.append(fragment)
    return ''.join(subject_parts)

def decode_filename(filename):
    decoded_fragments = decode_header(filename)
    filename_parts = []
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            encoding = encoding or 'utf-8'
            fragment = fragment.decode(encoding, errors='ignore')
        filename_parts.append(fragment)
    return ''.join(filename_parts)

def save_attachment(part, file_name):
    BASE_DIR = settings.BASE_DIR
    temp_dir = os.path.join(BASE_DIR, 'temp_files')
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, file_name)
    with open(file_path, 'wb') as f:
        f.write(part.get_payload(decode=True))
    return file_path
def parse_excel_file(file_path):
    try:
        logger.info(f'Начинаем обработку файла {file_path}')
        response = requests.get('http://localhost:8000/api/parsing-configs/')
        if response.status_code != 200:
            logger.error(f'Ошибка при получении настроек парсинга: {response.status_code}')
            return
        configs = response.json()

        for config in configs:
            column_mappings = config['column_mappings']
            df = pd.read_excel(file_path)

            df.rename(columns=column_mappings, inplace=True)

            if df.isnull().values.any():
                logger.error(f'Пропущенные значения в файле: {file_path}')
                continue

            if not df['quantity'].apply(lambda x: isinstance(x, (int, float))).all():
                logger.error(f'Неверный формат количества в файле: {file_path}')
                continue

            df['total_price'] = df['quantity'] * df['price']

            save_orders_to_db(df)
    except Exception as e:
        logger.error(f'Ошибка при обработке файла {file_path}: {str(e)}')

def save_orders_to_db(df):
    try:
        orders = []
        for _, row in df.iterrows():
            order = Order(
                order_id=row['order_id'],
                product_name=row['product_name'],
                quantity=row['quantity'],
                price=row['price'],
                order_date=row['order_date'],
                customer_email=row['customer_email'],
                total_price=row['total_price'],
            )
            orders.append(order)
        Order.objects.bulk_create(orders)
        logger.info(f'Сохранено {len(orders)} заказов в базу данных.')
    except Exception as e:
        logger.error(f'Ошибка при сохранении заказов в базу данных: {str(e)}')
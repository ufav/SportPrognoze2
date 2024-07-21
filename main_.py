import requests
from bs4 import BeautifulSoup
import sqlite3
from datetime import datetime, timedelta
import time
from httpx import AsyncClient
from telegram import Bot
from telegram.error import TelegramError
import asyncio
import logging
import platform
import re

base_url = "https://vprognoze.kz"
telegram_bot_token = "7384843477:AAFsitozSLRZvyFAuu_ZSEVSm1st_cnC0DA"
telegram_channel_id = "@SportPrognoze2"
telegram_id = "7449420157"
logging.basicConfig(level=logging.ERROR)
client = AsyncClient(timeout=30)
bot = Bot(token=telegram_bot_token)
last_pinned_message_id = None


async def send_telegram_message(message, pin=False, chat_id=telegram_channel_id):
    global last_pinned_message_id
    try:
        sent_message = await bot.send_message(chat_id=chat_id, text=message)
        if pin and chat_id == telegram_channel_id:
            if last_pinned_message_id:
                try:
                    await bot.unpin_chat_message(chat_id=telegram_channel_id, message_id=last_pinned_message_id)
                except TelegramError as e:
                    logging.error(f"Failed to unpin old message: {e}")
            await bot.pin_chat_message(chat_id=telegram_channel_id, message_id=sent_message.message_id,
                                       disable_notification=True)
            last_pinned_message_id = sent_message.message_id
    except Exception as e:
        logging.error(f"Failed to send message: {e}")
        await bot.send_message(chat_id=telegram_id, text=f"Ошибка при отправке сообщения: {str(e)}")
        await asyncio.sleep(30)


def parse_tip_page(link):
    tip_url = base_url + link
    try:
        tip_response = requests.get(tip_url)
        tip_html_content = tip_response.text
        tip_soup = BeautifulSoup(tip_html_content, 'html.parser')
        lasttips = tip_soup.find('div', id='lasttips')
        if not lasttips:
            return []
        tips = lasttips.find_all('div', class_='mini-tip')
        parsed_tips = []
        for tip in tips:
            try:
                outcome_type = 'unknown'
                if 'is-draw' in tip['class']:
                    outcome_type = 'draw'
                elif 'is-win' in tip['class']:
                    outcome_type = 'win'
                elif 'is-lose' in tip['class']:
                    outcome_type = 'lose'
                date_day = tip.find('div', class_='ui-date__day')
                date_hour = tip.find('div', class_='ui-date__hour')
                teams = tip.find('a', class_='mini-tip__teams')
                league = tip.find('div', class_='mini-tip__league')
                bet = tip.find('div', class_='mini-tip__bet')
                profit = tip.find('div', class_='mini-tip__profit')
                if date_day and date_hour and teams and league and bet and profit:
                    current_date = datetime.now()
                    current_year = current_date.year
                    current_month = current_date.month
                    forecast_month = int(date_day.text.split('-')[1])
                    if forecast_month < current_month:
                        forecast_year = current_year + 1
                    else:
                        forecast_year = current_year
                    date_str = f"{date_day.text} {date_hour.text} {forecast_year}"
                    date_time = datetime.strptime(date_str, "%d-%m %H:%M %Y").strftime("%Y-%m-%d %H:%M")
                    forecast_link = teams['href']
                    bet_text = bet.text.split(' @ ')
                    stake = bet_text[0]
                    odds = bet_text[1] if len(bet_text) > 1 else None
                    profit_text = profit.text.replace('Сумма', '').strip().split()[-1]
                    if profit_text.startswith('+'):
                        profit_text = profit_text[1:]
                    parsed_tips.append({
                        'outcome_type': outcome_type,
                        'date_time': date_time,
                        'forecast_link': forecast_link,
                        'teams': teams.text,
                        'league': league.text,
                        'stake': stake,
                        'odds': odds,
                        'profit': profit_text,
                    })
            except AttributeError:
                continue
        return parsed_tips
    except Exception as e:
        error_message = f"Ошибка при парсинге страницы {tip_url}: {str(e)}"
        logging.error(error_message)
        asyncio.run(send_telegram_message(error_message, chat_id=telegram_id))
        return []


def fetch_additional_details(forecast_link):
    try:
        match = re.search(r'/(\d+)-', forecast_link)
        if not match:
            logging.error(f"Не удалось извлечь ID из ссылки: {forecast_link}")
            return "ID не найден."

        numeric_id = match.group(1)
        full_id = f"news-id-{numeric_id}"
        forecast_response = requests.get(forecast_link)
        forecast_html_content = forecast_response.text
        forecast_soup = BeautifulSoup(forecast_html_content, 'html.parser')
        news_id_div = forecast_soup.find('div', id=full_id)
        #print(news_id_div)
        if news_id_div:
            news_id_html = str(news_id_div)
            parts = re.split(r'<br>|<br\s*/>', news_id_html)
            #print(len(parts))
            #print(parts[-1])
            if len(parts) > 1:
                last_part = parts[-1]
                clean_text = BeautifulSoup(last_part, 'html.parser').text.strip().split('<')[0]
                #print(clean_text)
                return clean_text
            else:
                return BeautifulSoup(news_id_html, 'html.parser').text.strip()
        else:
            return "-"
    except Exception as e:
        logging.error(f"Ошибка при получении описания: {str(e)}")
        return "-"


def tip_exists(cursor, forecast_link=None, teams=None, stake=None):
    if forecast_link:
        cursor.execute('SELECT outcome_type FROM tips WHERE forecast_link = ?', (forecast_link,))
    elif teams and stake:
        cursor.execute('SELECT outcome_type FROM tips WHERE teams = ? AND stake = ?', (teams, stake))
    else:
        return None
    return cursor.fetchone()


def get_statistics(cursor, days):
    end_date = datetime.now()
    start_date = (end_date - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    start_date_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
    end_date_str = end_date.strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('''
        SELECT COUNT(*), 
               SUM(CASE WHEN outcome_type = 'win' THEN 1 ELSE 0 END)
        FROM tips
        WHERE date_time BETWEEN ? AND ?
          AND outcome_type IN ('win', 'lose')
    ''', (start_date_str, end_date_str))
    total_bets, total_wins = cursor.fetchone()
    print(start_date_str)
    print(end_date_str)
    if total_bets == 0:
        total_wins = 0
    win_percentage = (total_wins / total_bets * 100) if total_bets else 0
    return total_bets, total_wins, round(win_percentage)


async def save_to_db(tips):
    conn = sqlite3.connect('tips.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS tips
                      (outcome_type TEXT, date_time DATETIME, forecast_link TEXT, teams TEXT, league TEXT, stake TEXT, odds TEXT, profit TEXT)''')
    update_occurred = False
    current_datetime = datetime.now()
    for tip in tips:
        existing_tip_by_link = tip_exists(cursor, forecast_link=tip['forecast_link'])
        existing_tip_by_team_stake = tip_exists(cursor, teams=tip['teams'], stake=tip['stake'])
        if existing_tip_by_link or existing_tip_by_team_stake:
            if existing_tip_by_link and existing_tip_by_link[0] != tip['outcome_type']:
                cursor.execute('UPDATE tips SET outcome_type = ? WHERE forecast_link = ?',
                               (tip['outcome_type'], tip['forecast_link']))
                outcome_emoji = "✅" if tip['outcome_type'] == 'win' else "❌"
                message = (
                    f"{tip['league']}\n"
                    f"{tip['teams']}\n"
                    f"{tip['stake']} - {tip['odds']}\n"
                    f"{outcome_emoji}"
                )
                await send_telegram_message(message)
                await asyncio.sleep(5)
                update_occurred = True
            continue
        tip_date_time = datetime.strptime(tip['date_time'], "%Y-%m-%d %H:%M")
        formatted_date_time = tip_date_time.strftime("%d.%m.%Y %H:%M")
        if tip['outcome_type'] == 'draw' and tip_date_time > current_datetime:
            description = fetch_additional_details(tip['forecast_link'])
            cursor.execute('INSERT INTO tips VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                           (tip['outcome_type'], tip['date_time'], tip['forecast_link'], tip['teams'],
                            tip['league'], tip['stake'], tip['odds'], tip['profit']))
            message = (
                f"{formatted_date_time} МСК\n"
                f"{tip['league']}\n"
                f"{tip['teams']}\n"
                f"{tip['stake']} - {tip['odds']}\n"
                f"{description}"
            )
            await send_telegram_message(message)
            await asyncio.sleep(5)
    time.sleep(1)
    conn.commit()
    time.sleep(1)
    if update_occurred:
        daily_stats = get_statistics(cursor, 0)
        weekly_stats = get_statistics(cursor, 6)
        monthly_stats = get_statistics(cursor, 29)
        stats_message = (
            f"Сегодня: {daily_stats[0]} ставок, {daily_stats[1]} выиграло, {daily_stats[2]}% побед\n"
            f"За неделю: {weekly_stats[0]} ставок, {weekly_stats[1]} выиграло, {weekly_stats[2]}% побед\n"
            f"За месяц: {monthly_stats[0]} ставок, {monthly_stats[1]} выиграло, {monthly_stats[2]}% побед")
        await send_telegram_message(stats_message, pin=True)
    conn.close()


async def main():
    try:
        response = requests.get(base_url)
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        rows = soup.find_all('tr', onclick=True)
        links = [row['onclick'].split("'")[1] for row in rows]
        all_tips = []
        for link in links:
            tips = parse_tip_page(link)
            all_tips.extend(tips)
        await save_to_db(all_tips)
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        await send_telegram_message(f"Ошибка при выполнении main: {str(e)}", chat_id=telegram_id)


def run():
    try:
        if platform.system() == 'Windows':
            loop = asyncio.ProactorEventLoop()
            asyncio.set_event_loop(loop)
        else:
            loop = asyncio.get_event_loop()
        loop.run_until_complete(main())
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(main())
        else:
            raise


if __name__ == "__main__":
    run()

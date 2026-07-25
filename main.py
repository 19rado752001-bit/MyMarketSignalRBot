import asyncio
import logging
import sys
import ccxt.async_support as ccxt  # Ասինխրոն CCXT
import pandas as pd
import pandas_ta as ta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Տեղադրեք ձեր Telegram բոտի թոքենը այստեղ
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

logging.basicConfig(level=logging.INFO)

# Ասինխրոն միացում Binance-ին
exchange = ccxt.binance({'enableRateLimit': True})

# Հասանելի զույգեր և թայմֆրեյմներ
SYMBOLS = {
    "BTC": "BTC/USDT",
    "ETH": "ETH/USDT",
    "SOL": "SOL/USDT",
    "EUR": "EUR/USDT",  # Ֆորեքս զույգ (կախված բորսայի հասանելիությունից)
}

TIMEFRAMES = ["5s", "10s", "1m", "5s", "15m", "1h"]


async def fetch_and_analyze(symbol: str, timeframe: str):
  """Տվյալների ներբեռնում և ինդիկատորների հաշվարկ"""
  try:
    # Վայրկյանայինների համար վերցնում ենք 1m բազային տվյալներ և վերամշակում
    tf_to_fetch = (
        "1m" if timeframe in ["5s", "10s", "5s"] else timeframe
    )

    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=tf_to_fetch, limit=100)
    await exchange.close()

    df = pd.DataFrame(
        ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

    # Եթե վայրկյանային է, կատարում ենք resample
    if timeframe == "5s":
      df.set_index("timestamp", inplace=True)
      df = df.resample("5s").agg(
          {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
      ).dropna().reset_index()
    elif timeframe == "10s":
      df.set_index("timestamp", inplace=True)
      df = df.resample("10s").agg(
          {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
      ).dropna().reset_index()

    if len(df) < 20:
      return f"⏳ Տվյալները բավարար չեն ({symbol} - {timeframe})..."

    # Pandas-TA ինդիկատորներ
    df["rsi"] = ta.rsi(df["close"], length=14)
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    df = pd.concat([df, macd], axis=1)

    bb = ta.bbands(df["close"], length=20, std=2)
    df = pd.concat([df, bb], axis=1)

    last_rsi = df["rsi"].iloc[-1]
    last_macd = df["MACD_12_26_9"].iloc[-1]
    last_signal = df["MACDs_12_26_9"].iloc[-1]

    # Ազդանշանի տրամաբանություն (Scoring / Confluence)
    if last_rsi > 50 and last_macd > last_signal:
      return (
          f"🟢 **ԳՆԵԼ (BUY)**\n💱 Զույգ: **{symbol}**\n⏱ Թայմֆրեյմ: **{timeframe}**\n📊"
          f" RSI: {last_rsi:.2f}\n📈 Մոմի ուղղությունը՝ Աճող 🚀"
      )
    elif last_rsi < 50 and last_macd < last_signal:
      return (
          f"🔴 **ՎԱՃԱՌԵԼ (SELL)**\n💱 Զույգ: **{symbol}**\n⏱ Թայմֆրեյմ:"
          f" **{timeframe}**\n📊 RSI: {last_rsi:.2f}\n📉 Մոմի ուղղությունը՝"
          f" Նվազող 🔻"
      )
    else:
      return (
          f"⏳ **ՍՊԱՍԵԼ / Չեզոք**\n💱 Զույգ: **{symbol}**\n⏱ Թայմֆրեյմ:"
          f" **{timeframe}**\n📊 RSI: {last_rsi:.2f} (Անհամաձայնություն)"
      )

  except Exception as e:
    return f"❌ Սխալ տվյալների մշակման ժամանակ: {str(e)}"


# Telegram Բոտի կարգավորում
bot = Bot(token=TOKEN)
dp = Dispatcher()


@dp.message(Command("start"))
async def send_welcome(message: types.Message):
  kb = [
      [
          InlineKeyboardButton(text="🪙 BTC / USDT", callback_data="sym_BTC"),
          InlineKeyboardButton(text="🪙 ETH / USDT", callback_data="sym_ETH"),
      ],
      [
          InlineKeyboardButton(text="🪙 SOL / USDT", callback_data="sym_SOL"),
          InlineKeyboardButton(text="💱 EUR / USDT", callback_data="sym_EUR"),
      ],
  ]
  keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
  await message.answer(
      "Բարև ձեզ 🤖։ Ընտրեք ակտիվը (զույգը) վերլուծության համար:",
      reply_markup=keyboard,
  )


@dp.callback_query(F.data.startswith("sym_"))
async def choose_symbol(callback: types.CallbackQuery):
  symbol_key = callback.data.split("_")[1]
  symbol_name = SYMBOLS[symbol_key]

  kb = []
  row = []
  for tf in TIMEFRAMES:
    row.append(
        InlineKeyboardButton(
            text=tf, callback_data=f"tf_{symbol_key}_{tf}"
        )
    )
    if len(row) == 3:
      kb.append(row)
      row = []
  if row:
    kb.append(row)

  keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
  await callback.message.edit_text(
      f"Ընտրված է՝ **{symbol_name}** 📊\nԱյժմ ընտրեք ժամանակահատվածը"
      " (Timeframe):",
      reply_markup=keyboard,
      parse_mode="Markdown",
  )
  await callback.answer()


@dp.callback_query(F.data.startswith("tf_"))
async def show_signal(callback: types.CallbackQuery):
  _, symbol_key, timeframe = callback.data.split("_")
  symbol_name = SYMBOLS[symbol_key]

  await callback.message.edit_text(
      f"⏳ Վերլուծվում է {symbol_name} ({timeframe})..."
  )

  result = await fetch_and_analyze(symbol_name, timeframe)
  await callback.message.edit_text(result, parse_mode="Markdown")
  await callback.answer()


async def main():
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())

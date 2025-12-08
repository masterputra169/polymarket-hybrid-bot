# 🤖 Polymarket Hybrid Trading Bot

Automated trading bot for Polymarket's BTC 15-minute "Up or Down" markets.

## ⚠️ Disclaimer

**Educational purposes only. Use at your own risk.**

## ✨ Features

- 🔍 Automatic market discovery
- 📊 Real-time price monitoring  
- 💰 Pair trading strategy
- 🎯 Last-second sniping
- 🔐 Secure (keys never leave your machine)

## 🚀 Quick Start
```bash
# 1. Clone
git clone https://github.com/masterputra169/polymarket-hybrid-bot.git

# 2. Install
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env with your credentials

# 4. Run
python main_hybrid.py
```

## 📊 Strategy

- **Pair Trading**: Buy YES+NO when pair cost < $0.98
- **Sniping**: Execute trades in final 60 seconds

## ⚙️ Configuration

Edit `.env`:
```bash
PRIVATE_KEY=your_key_here
PROXY_ADDRESS=0xYourAddress
ORDER_SIZE_USD=1.0
DRY_RUN=true
```

## 🔒 Security

- ✅ Never commit `.env` file
- ✅ Start with small amounts
- ✅ Use dry-run mode first

## 📚 Resources

- [Polymarket Docs](https://docs.polymarket.com)
- [CLOB API](https://docs.polymarket.com/developers/CLOB/introduction)

## 📝 License

MIT License

"""
USDC Allowance Setup Script
MUST run this once before trading

This authorizes Polymarket's exchange contract to spend your USDC
Uses web3.py to interact directly with Polygon blockchain
"""
import os
import sys
from dotenv import load_dotenv
from web3 import Web3

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import setup_logger

load_dotenv()

# Contract addresses on Polygon Mainnet
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_CTF_EXCHANGE = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
NEG_RISK_ADAPTER = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"

# ERC20 ABI (minimal - just approve function)
ERC20_ABI = [
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]

def main():
    """Setup USDC allowances"""
    
    logger = setup_logger("Approve")
    
    print("""
╔═══════════════════════════════════════════════════════════════╗
║              USDC ALLOWANCE SETUP                             ║
║                                                               ║
║  This script authorizes Polymarket to spend your USDC        ║
║  ⚠️  REQUIRED before the bot can trade                       ║
╚═══════════════════════════════════════════════════════════════╝
    """)
    
    # Check required vars
    private_key = os.getenv("PRIVATE_KEY")
    
    if not private_key:
        logger.error("❌ Missing PRIVATE_KEY in .env")
        sys.exit(1)
    
    # Add 0x prefix if not present
    if not private_key.startswith('0x'):
        private_key = '0x' + private_key
    
    try:
        # Connect to Polygon
        logger.info("📡 Connecting to Polygon...")
        
        # Use public RPC
        rpc_url = os.getenv("RPC_URL", "https://polygon-rpc.com")
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        
        if not w3.is_connected():
            logger.error("❌ Failed to connect to Polygon")
            logger.info("💡 Try using Infura or Alchemy RPC URL")
            sys.exit(1)
        
        logger.info("✅ Connected to Polygon")
        
        # Get account from private key
        account = w3.eth.account.from_key(private_key)
        address = account.address
        
        logger.info(f"   Wallet: {address[:10]}...{address[-8:]}")
        
        # Check balance
        balance = w3.eth.get_balance(address)
        balance_matic = w3.from_wei(balance, 'ether')
        
        logger.info(f"   MATIC Balance: {balance_matic:.4f}")
        
        if balance_matic < 0.01:
            logger.warning("⚠️ Low MATIC balance!")
            logger.warning("   You need MATIC for gas fees")
            logger.warning("   Get some from: https://wallet.polygon.technology/")
        
        # Setup USDC contract
        usdc_contract = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
        
        # Unlimited approval amount
        max_approval = 2**256 - 1
        
        # Spenders to approve
        spenders = {
            "CTF Exchange": CTF_EXCHANGE,
            "Neg Risk CTF Exchange": NEG_RISK_CTF_EXCHANGE,
            "Neg Risk Adapter": NEG_RISK_ADAPTER
        }
        
        logger.info("\n🔍 Checking current allowances...")
        
        for name, spender in spenders.items():
            current_allowance = usdc_contract.functions.allowance(
                address, spender
            ).call()
            
            if current_allowance > 0:
                logger.info(f"   ✅ {name}: Already approved")
            else:
                logger.info(f"   ⚠️ {name}: Not approved")
        
        # Ask for confirmation
        logger.info("\n⚙️ This will set USDC allowances for Polymarket contracts")
        response = input("Continue? (y/n): ").strip().lower()
        
        if response != 'y':
            logger.info("❌ Setup cancelled")
            sys.exit(0)
        
        # Set allowances
        logger.info("\n💸 Setting allowances...")
        
        success_count = 0
        
        for name, spender in spenders.items():
            logger.info(f"\n   Setting allowance for {name}...")
            
            try:
                # Check current allowance
                current = usdc_contract.functions.allowance(address, spender).call()
                
                if current > max_approval // 2:
                    logger.info(f"   ✅ {name}: Already has sufficient allowance")
                    success_count += 1
                    continue
                
                # Build transaction
                tx = usdc_contract.functions.approve(
                    spender,
                    max_approval
                ).build_transaction({
                    'from': address,
                    'nonce': w3.eth.get_transaction_count(address),
                    'gas': 100000,
                    'gasPrice': w3.eth.gas_price,
                })
                
                # Sign transaction
                signed_tx = w3.eth.account.sign_transaction(tx, private_key)
                
                # Send transaction
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                
                logger.info(f"   📤 Transaction sent: {tx_hash.hex()}")
                logger.info(f"   ⏳ Waiting for confirmation...")
                
                # Wait for receipt
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
                
                if receipt['status'] == 1:
                    logger.info(f"   ✅ {name}: Approved successfully!")
                    success_count += 1
                else:
                    logger.error(f"   ❌ {name}: Transaction failed")
                
            except Exception as e:
                logger.error(f"   ❌ {name}: {e}")
        
        # Summary
        logger.info("\n" + "="*60)
        
        if success_count == len(spenders):
            logger.info("✅ SUCCESS!")
            logger.info("   All allowances have been set")
            logger.info("   Bot is now ready to trade")
            logger.info("\n💡 Next step: python main_hybrid.py")
        elif success_count > 0:
            logger.warning(f"⚠️ PARTIAL SUCCESS")
            logger.warning(f"   {success_count}/{len(spenders)} allowances set")
            logger.warning("   Bot may work but some markets might fail")
        else:
            logger.error("❌ FAILED")
            logger.error("   No allowances were set")
            logger.error("   Please check:")
            logger.error("   - Your wallet has MATIC for gas")
            logger.error("   - Your private key is correct")
            logger.error("   - RPC connection is stable")
    
    except Exception as e:
        logger.error(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
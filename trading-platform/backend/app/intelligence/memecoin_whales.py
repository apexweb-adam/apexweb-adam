"""Curated whale / smart-money wallets for memecoin and crypto intel tracking."""

from __future__ import annotations

# Public exchange, market-maker, and high-signal Ethereum wallets (Etherscan-labeled).
DEFAULT_ETH_WHALE_ADDRESSES: tuple[str, ...] = (
  "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",  # vitalik.eth
  "0x171e6ba0f64ccc9fe7dafbea59f35bafbcdafe94",  # Wintermute
  "0x28C6c06298dDbDbF230B039c3c89C23E6749FaFa",  # Binance 14
  "0x47ac0Fb4F2D84898e4D9E7fE6e9230db20AEad85",  # Binance-Peg USDT
  "0x21a31Ee1afC51d94C2eFcCAa2092aD1028285549",  # Binance 8
  "0x3ddfa8ec3052539b6c9549f452ca3eb54d4b2655",  # Justin Sun
  "0xDFd5293D8e347dFe59E90eFd55b2956a1343963d",  # Binance 17
  "0xBE0eB53F46cd790Cf13859B60fCD155e0EfF8a26",  # Binance 7
  "0xf977814e90da44bfa03b6295a0616a897441acec",  # Binance cold
  "0x564286836092D35eA710f14a391bB2Eb0837169",  # GSR Markets
  "0x40Ec5E71Bb04E3eFC2f1f3297fCC8cF83aB80157",  # Crypto.com 14
  "0x6262998CaedAe61104Ff2Ca4fd45bAAAd44f41Ac",  # Bitfinex
)

# Solana exchange / MM wallets — memecoin flow often routes through these.
DEFAULT_SOLANA_WHALE_ADDRESSES: tuple[str, ...] = (
  "5tzFkiKscXHK5ZXCGbXZxdw7gTjjD1mBwuoFbhUvuAi9",  # Binance hot wallet (SOL)
  "H6ARHf6YXhGYeQfUzQNGk6rDNnLBQKrenN712K4AQJEG",  # Wintermute (SOL)
  "AC5RDfqfM4Si9JDM1GmKnd6oc6o56a25GSv6uQJBATqN",  # Jump Crypto (SOL)
  "2AQdpHJ2JpcEgPiATMGQUBpUjJdkvT35nocSx8dH1kE",  # Coinbase hot (SOL)
)
